from typing import List, Optional
from app.schemas.planning import DecompositionPlan, RouteDecision, DecompositionValidationResult
from app.core.logger import logger


class DecompositionValidator:
    def __init__(self, min_goal_length: int = 5, min_query_length: int = 10):
        self.min_goal_length = min_goal_length
        self.min_query_length = min_query_length
    
    def validate(self, plan: DecompositionPlan, route: Optional[RouteDecision] = None) -> DecompositionValidationResult:
        warnings: List[str] = []
        errors: List[str] = []
        incomplete_tasks: List[str] = []
        
        for task in plan.subtasks:
            if len(task.goal.strip()) < self.min_goal_length:
                warnings.append(f"Task {task.id} has incomplete goal")
                incomplete_tasks.append(task.id)
            
            if len(task.query.strip()) < self.min_query_length:
                warnings.append(f"Task {task.id} has incomplete query")
                incomplete_tasks.append(task.id)
        
        has_cycles = self._detect_cycles(plan)
        if has_cycles:
            errors.append("Dependency graph has cycles")
        
        if route and route.intent == "comparison":
            retrieval_tasks = [t for t in plan.subtasks if t.type == "retrieval"]
            if len(retrieval_tasks) < 2:
                warnings.append("Comparison queries should have at least 2 retrieval tasks")
        
        if len(plan.subtasks) == 0:
            errors.append("Decomposition has no subtasks")
        
        if len(plan.subtasks) == 1 and route and route.query_type == "multi_hop":
            warnings.append("Multi-hop query has only 1 subtask - may need more decomposition")
        
        is_valid = len(errors) == 0
        
        if warnings or errors:
            logger.info(f"Decomposition validation: {len(warnings)} warnings, {len(errors)} errors")
        
        return DecompositionValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            has_cycles=has_cycles,
            incomplete_tasks=incomplete_tasks
        )
    
    def _detect_cycles(self, plan: DecompositionPlan) -> bool:
        task_ids = {task.id for task in plan.subtasks}
        adjacency = {task.id: [] for task in plan.subtasks}
        
        for task in plan.subtasks:
            for dep_id in task.depends_on:
                if dep_id in task_ids:
                    adjacency[dep_id].append(task.id)
        
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for task_id in task_ids:
            if task_id not in visited:
                if has_cycle(task_id):
                    return True
        
        return False
