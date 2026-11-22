# Claude skill

Craticula has a skill for Claude. A skill is a folder of plain-text instructions that Claude reads before it helps you. This one teaches Claude how to add Craticula to a C# project.

To use it, install it with the two commands below, or copy its folder by hand. Then ask Claude to add Craticula to your project. When you are done, read [The safety model](safety-model.html) to see what Craticula protects.

## Two ways to install

The first way is a Claude Code plugin. Run both commands in a terminal:

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

The first command adds the Craticula marketplace from the repository. The second installs the skill from it. The commands are the same in every language of this site.

The second way is a copy. Take the folder `skills/craticula` from the [Craticula repository](https://github.com/pluries/craticula) and put it in `~/.claude/skills/craticula/`. That is your personal skills folder, so the skill works in every project you open. To use it in one project only, put the folder in that project's own skills folder instead.

## What the skill does

- It tells Claude which Craticula packages your project needs.
- It shows how to declare a schema, parse the grid request and compile it into a query.
- It treats the adapters that run queries as optional.
- It points Claude to the same facts as this site, so the two do not drift apart.

The skill keeps to the library's safety rules and limits. See [The safety model](safety-model.html) and [Limits](limits.html).

## What it does not do

The skill is text. It cannot run code, open a connection or change a file. Claude makes any change to your project in your own session, under your own permission settings.

The skill does not name a version. It tells Claude to use the latest package on nuget.org, or the version your project already uses.

## Languages

The skill covers the C# library, which is the reference implementation. No TypeScript, Python or Go implementation exists yet. Their quickstart pages say so: [Python](quickstart-python.html), [Go](quickstart-go.html) and [TypeScript](quickstart-typescript.html). The skill offers the C# library instead.

## Which copy is official

The official copy is the `skills/craticula` folder in the [Craticula repository](https://github.com/pluries/craticula). Releases of the packages carry tags that start with `dotnet-v`. Report a security problem as [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md) describes.

A fork, or a copy from another place, has none of this provenance. Compare it with the repository before you rely on it.

## What to expect from Claude

Agent behaviour is not guaranteed: the skill is text, and the proof that an agent reaches a working run is one manual demonstration, not an automated test.

Read the code Claude writes before you run it, as you would for any code.

## Further reading

- [Dialects and providers](dialects-and-providers.html) says which databases Craticula compiles for and how they differ.
- [Limits](limits.html) lists the caps on request size and complexity.
- [The safety model](safety-model.html) lists what Craticula protects and what it does not.
- [The C# quickstart](quickstart-csharp.html) shows the same steps by hand.
