import type { User } from "./user";

export interface Comment {
  id: string;
  taskId: string;
  authorId: User["id"];
  content: string;
  createdAt: string;
  updatedAt?: string;
}
