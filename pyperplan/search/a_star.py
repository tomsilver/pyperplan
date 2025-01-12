#
# This file is part of pyperplan.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

"""
Implements the A* (a-star) and weighted A* search algorithm.
"""

from difflib import SequenceMatcher

import heapq
import logging
import time

from . import searchspace


def ordered_node_astar(node, h, node_tiebreaker):
    """
    Creates an ordered search node (basically, a tuple containing the node
    itself and an ordering) for A* search.

    @param node The node itself.
    @param heuristic A heuristic function to be applied.
    @param node_tiebreaker An increasing value to prefer the value first
                           inserted if the ordering is the same.
    @returns A tuple to be inserted into priority queues.
    """
    f = node.g + h
    return (f, h, node_tiebreaker, node)


def ordered_node_weighted_astar(weight):
    """
    Creates an ordered search node (basically, a tuple containing the node
    itself and an ordering) for weighted A* search (order: g+weight*h).

    @param weight The weight to be used for h
    @param node The node itself
    @param h The heuristic value
    @param node_tiebreaker An increasing value to prefer the value first
                           inserted if the ordering is the same.
    @returns A tuple to be inserted into priority queues
    """
    """
    Calling ordered_node_weighted_astar(42) actually returns a function (a
    lambda expression) which is the *actual* generator for ordered nodes.
    Thus, a call like
        ordered_node_weighted_astar(42)(node, heuristic, tiebreaker)
    creates an ordered node with weighted A* ordering and a weight of 42.
    """
    return lambda node, h, node_tiebreaker: (
        node.g + weight * h,
        h,
        node_tiebreaker,
        node,
    )


def ordered_node_greedy_best_first(node, h, node_tiebreaker):
    """
    Creates an ordered search node (basically, a tuple containing the node
    itself and an ordering) for greedy best first search (the value with lowest
    heuristic value is used).

    @param node The node itself.
    @param h The heuristic value.
    @param node_tiebreaker An increasing value to prefer the value first
                           inserted if the ordering is the same.
    @returns A tuple to be inserted into priority queues.
    """
    f = h
    return (f, h, node_tiebreaker, node)


def greedy_best_first_search(task, heuristic, timeout, use_relaxed_plan=False,
                             partial_plans=None, partial_plan_guidance_method="init-queue"):
    """
    Searches for a plan in the given task using greedy best first search.

    @param task The task to be solved.
    @param heuristic A heuristic callable which computes the estimated steps
                     from a search node to reach the goal.
    """
    return astar_search(
        task, heuristic, timeout, ordered_node_greedy_best_first, use_relaxed_plan,
        partial_plans=partial_plans,
        partial_plan_guidance_method=partial_plan_guidance_method,
    )


def weighted_astar_search(task, heuristic, timeout, weight=5, use_relaxed_plan=False,
                          partial_plans=None, partial_plan_guidance_method="init-queue"):
    """
    Searches for a plan in the given task using A* search.

    @param task The task to be solved.
    @param heuristic  A heuristic callable which computes the estimated steps.
                      from a search node to reach the goal.
    @param weight A weight to be applied to the heuristics value for each node.
    """
    return astar_search(
        task, heuristic, timeout, ordered_node_weighted_astar(weight), use_relaxed_plan,
        partial_plans=partial_plans, partial_plan_guidance_method=partial_plan_guidance_method
    )


def astar_search(
    task, heuristic, timeout, make_open_entry=ordered_node_astar,
    use_relaxed_plan=False, partial_plans=None,
    partial_plan_guidance_method="init-queue",
):
    """
    Searches for a plan in the given task using A* search.

    @param task The task to be solved
    @param heuristic  A heuristic callable which computes the estimated steps
                      from a search node to reach the goal.
    @param make_open_entry An optional parameter to change the bahavior of the
                           astar search. The callable should return a search
                           node, possible values are ordered_node_astar,
                           ordered_node_weighted_astar and
                           ordered_node_greedy_best_first with obvious
                           meanings.
    """
    start_time = time.time()
    # Initialize nodes created to 1 for the root.
    metrics = {"nodes_expanded": 0, "nodes_created": 1}
    open = []
    state_cost = {task.initial_state: 0}
    node_tiebreaker = 0

    root = searchspace.make_root_node(task.initial_state)
    init_h = heuristic(root)
    heapq.heappush(open, make_open_entry(root, init_h, node_tiebreaker))
    logging.info(f"Initial h value: {init_h}")

    assert partial_plan_guidance_method != "edit-distance", "DEPRECATED"
    if partial_plans is not None and "init-queue" in partial_plan_guidance_method:
        op_map = {op.name: op for op in task.operators}
        for partial_plan in partial_plans:
            node = root
            for op_name in partial_plan:
                try:
                    op = op_map[op_name]
                except KeyError:
                    if partial_plan_guidance_method == "init-queue-continue":
                        continue
                    else:
                        assert partial_plan_guidance_method == "init-queue-break"
                        break
                # If we've reached an inapplicable operator, skip.
                if not op.applicable(node.state):
                    # print(f"Hit inapplicable op: {op}")
                    # print(f"Missing preconditions: {op.preconditions - node.state})")
                    # import ipdb; ipdb.set_trace()
                    if partial_plan_guidance_method == "init-queue-continue":
                        continue
                    else:
                        assert partial_plan_guidance_method == "init-queue-break"
                        break
                succ_state = op.apply(node.state)
                # print(f"Applying op: {op}")
                # print(f"State now: {succ_state}")
                succ_node = searchspace.make_child_node(node, op, succ_state)
                h = heuristic(succ_node)
                if h == float("inf"):
                    # If we've reached a dead-end, might as well stop now.
                    break
                old_succ_g = state_cost.get(succ_state, float("inf"))
                if succ_node.g < old_succ_g:
                    # We either never saw succ_state before, or we found a
                    # cheaper path to succ_state than previously.
                    node_tiebreaker += 1
                    heapq.heappush(open, make_open_entry(succ_node, h, node_tiebreaker))
                    metrics["nodes_created"] += 1
                    state_cost[succ_state] = succ_node.g
                # Update node
                node = succ_node

    # print(f"Nodes added to queue: {len(open)}")
    # import ipdb; ipdb.set_trace()

    besth = init_h
    counter = 0
    expansions = 0

    while open:
        
        # Failing due to timeout.
        if time.time() - start_time >= timeout:
            return None, metrics

        (f, h, _tie, pop_node) = heapq.heappop(open)
        if h < besth:
            besth = h
            logging.debug(f"Found new best h: {besth} after {counter} expansions")

        pop_state = pop_node.state
        # Only expand the node if its associated cost (g value) is the lowest
        # cost known for this state. Otherwise we already found a cheaper
        # path after creating this node and hence can disregard it.
        if state_cost[pop_state] == pop_node.g:
            expansions += 1
            metrics["nodes_expanded"] += 1

            if task.goal_reached(pop_state):
                logging.info("Goal reached. Start extraction of solution.")
                logging.info("%d Nodes expanded" % expansions)
                return pop_node.extract_solution(), metrics
            rplan = None
            if use_relaxed_plan:
                (rh, rplan) = heuristic.calc_h_with_plan(
                    searchspace.make_root_node(pop_state)
                )
                logging.debug("relaxed plan %s " % rplan)

            for op, succ_state in task.get_successor_states(pop_state):
                if use_relaxed_plan:
                    if rplan and not op.name in rplan:
                        # ignore this operator if we use the relaxed plan
                        # criterion
                        logging.debug(
                            "removing operator %s << not a "
                            "preferred operator" % op.name
                        )
                        continue
                    else:
                        logging.debug("keeping operator %s" % op.name)

                succ_node = searchspace.make_child_node(pop_node, op, succ_state)
                h = heuristic(succ_node)
                if h == float("inf"):
                    # don't bother with states that can't reach the goal anyway
                    continue
                old_succ_g = state_cost.get(succ_state, float("inf"))
                if succ_node.g < old_succ_g:
                    # We either never saw succ_state before, or we found a
                    # cheaper path to succ_state than previously.
                    node_tiebreaker += 1
                    heapq.heappush(open, make_open_entry(succ_node, h, node_tiebreaker))
                    metrics["nodes_created"] += 1
                    state_cost[succ_state] = succ_node.g

        counter += 1
    logging.info("No operators left. Task unsolvable.")
    logging.info("%d Nodes expanded" % expansions)
    return None, metrics
