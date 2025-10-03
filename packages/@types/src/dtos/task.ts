import type { User } from "./user";
import type { Comment } from "./comment";

export type TaskStatus = "pending" | "in_progress" | "completed" | "archived";

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  createdAt: string;
  updatedAt?: string;
  dueDate?: string;
  assignedTo?: User["id"];
  comments?: Comment[];
}
