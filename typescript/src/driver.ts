import { createInterface } from "node:readline";

import { answerFor, assertSupportedNode, helloLine } from "./protocol.js";

/**
 * The TypeScript conformance driver (skeleton): the loop of `spec/conformance-runner.md` §8 over JSON Lines on stdin and stdout.
 * stdout carries protocol lines and nothing else; diagnostics go to stderr.
 */
function main(): void {
  try {
    assertSupportedNode(process.versions.node);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 2;
    return;
  }

  process.stdout.write(`${helloLine()}\n`);

  const reader = createInterface({ input: process.stdin, crlfDelay: Infinity });
  let lineNumber = 0;
  reader.on("line", (line) => {
    lineNumber += 1;
    if (line.trim().length === 0) {
      return;
    }
    const outcome = answerFor(line);
    if ("unanswerable" in outcome) {
      process.stderr.write(`Craticula TypeScript driver: request line ${lineNumber} cannot be answered: ${outcome.unanswerable}.\n`);
      process.exitCode = 1;
      reader.close();
      process.stdin.destroy();
      return;
    }
    process.stdout.write(`${outcome.answer}\n`);
  });
}

main();
