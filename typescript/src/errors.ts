export type ErrorKind = "UnknownField" | "Unsupported" | "InvalidRequest" | "InvalidSchema" | "LimitExceeded";

/** A request or schema the compiler refuses. The kind is a free label for the runner's report; the message says why. */
export class CompileError extends Error {
  readonly kind: ErrorKind;

  constructor(kind: ErrorKind, message: string) {
    super(message);
    this.name = "CompileError";
    this.kind = kind;
  }
}
