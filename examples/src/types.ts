/**
 * Core domain types and API contract interfaces for Tasks.
 */

/**
 * Task priority classification.
 */
export type TaskPriority = "low" | "medium" | "high" | "critical";

/**
 * Task operational lifecycle status.
 */
export enum TaskStatus {
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  COMPLETED = "completed",
}

/**
 * Persisted task entity model.
 */
export interface TaskItem {
  id: string;
  title: string;
  completed: boolean;
  priority?: TaskPriority;
  tags?: string[];
  createdAt: string;
}

/**
 * Input payload for task creation.
 */
export interface CreateTaskInput {
  title: string;
  priority?: TaskPriority;
  tags?: string[];
}

/**
 * Fetch tasks filtered by completion status and optional limit.
 *
 * @param completed - Filter by completed flag
 * @param limit - Maximum number of items to return
 * @returns Array of matching TaskItem objects
 */
export async function listTasks(completed?: boolean, limit?: number): Promise<TaskItem[]> {
  return [];
}

/**
 * Fetch a single task by ID via arrow function.
 */
export const fetchTaskById = async (id: string): Promise<TaskItem | null> => {
  return null;
};
