export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** 409 from a HITL signal: the artifact changed after the approval request was opened. */
export class StaleArtifactError extends ApiError {
  constructor(readonly currentHash?: string) {
    super(409, "The artifact changed after this request was opened. Reload to review the latest version.", "stale_artifact_hash");
    this.name = "StaleArtifactError";
  }
}

/** 412 from a profile PATCH: someone else saved the profile first. */
export class PreconditionFailedError extends ApiError {
  constructor() {
    super(412, "The profile was updated by someone else. Reload and re-apply your changes.", "etag_mismatch");
    this.name = "PreconditionFailedError";
  }
}

export const errorMessage = (err: unknown): string =>
  err instanceof Error ? err.message : "Something went wrong. Try again.";
