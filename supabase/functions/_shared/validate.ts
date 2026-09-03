import { errorResponse } from "./cors.ts";

export function rejectExtraKeys(
  body: Record<string, unknown>,
  allowedKeys: string[],
): void {
  for (const key of Object.keys(body)) {
    if (!allowedKeys.includes(key)) {
      throw errorResponse(`Unexpected field: ${key}`, 400);
    }
  }
}

export async function parseJsonBody(req: Request): Promise<Record<string, unknown>> {
  try {
    const body = await req.json();
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      throw errorResponse("Invalid JSON body", 400);
    }
    return body as Record<string, unknown>;
  } catch (err) {
    if (err instanceof Response) throw err;
    throw errorResponse("Invalid JSON body", 400);
  }
}

export function requirePositiveInt(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw errorResponse(`${field} must be a positive integer`, 400);
  }
  return value;
}

export function requireNonNegativeInt(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw errorResponse(`${field} must be a non-negative integer`, 400);
  }
  return value;
}

export function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw errorResponse(`${field} must be a non-empty string`, 400);
  }
  return value;
}
