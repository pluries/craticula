---
translates: claude-skill
title: Claude 技能
description: Craticula 为 Claude 提供的技能：它是什么、如何安装、能做什么，以及哪份副本是官方的。
source_fingerprint: 63b1738da63b9355a6d5c64ab072a81d4f2fa969df1e3817fc06403b6cb6dba0
drafter: claude
drafted_on: 2026-11-22
status: approved
---
# Claude 技能 {#claude-skill}

Craticula 为 Claude 提供了一个技能。技能是一个由纯文本说明组成的文件夹，Claude 会在帮助您之前先阅读它。这个技能教 Claude 如何把 Craticula 添加到 C# 项目中。

使用时，用下面的两条命令安装，或手动复制它的文件夹。然后请 Claude 把 Craticula 添加到您的项目。完成后，请阅读[安全模型](safety-model.html)，了解 Craticula 保护什么。

## 两种安装方式 {#two-ways-to-install}

第一种方式是 Claude Code 插件。请在终端中运行这两条命令：

```text
claude plugin marketplace add pluries/craticula
claude plugin install craticula@craticula
```

第一条命令从代码仓库添加 Craticula 市场。第二条命令从中安装该技能。这些命令在本网站的每种语言中都相同。

第二种方式是复制。从 [Craticula 代码仓库](https://github.com/pluries/craticula)中取出文件夹 `skills/craticula`，放到 `~/.claude/skills/craticula/` 中。那是您个人的技能文件夹，因此该技能在您打开的每个项目中都可用。如果只想在某一个项目中使用，请改为把该文件夹放进该项目自己的技能文件夹。

## 技能能做什么 {#what-the-skill-does}

- 它告诉 Claude 您的项目需要哪些 Craticula 包。
- 它演示如何声明模式、解析表格请求，并把请求编译为查询。
- 它把执行查询的适配器视为可选项。
- 它让 Claude 参考与本网站相同的事实，使两者不会逐渐偏离。

该技能遵守本库的安全规则和限制。请参阅[安全模型](safety-model.html)和[限制](limits.html)。

## 它不做什么 {#what-it-does-not-do}

该技能只是文本。它不能运行代码、打开连接或修改文件。对您项目的任何改动，都由 Claude 在您自己的会话中、按您自己的权限设置来进行。

该技能不写明版本。它让 Claude 使用 nuget.org 上最新的包，或您的项目已在使用的版本。

## 语言 {#languages}

该技能涵盖 C# 库，它是参考实现。目前还没有 TypeScript、Python 或 Go 的实现。它们的快速入门页面也这样说明：[Python](quickstart-python.html)、[Go](quickstart-go.html) 和 [TypeScript](quickstart-typescript.html)。该技能会改为提供 C# 库。

## 哪份副本是官方的 {#which-copy-is-official}

官方副本是 [Craticula 代码仓库](https://github.com/pluries/craticula)中的 `skills/craticula` 文件夹。这些包的发布版本带有以 `dotnet-v` 开头的标签。请按 [SECURITY.md](https://github.com/pluries/craticula/blob/main/SECURITY.md) 的说明报告安全问题。

分叉（fork）或来自其他地方的副本不具备这些来源保证。在依赖它之前，请先与代码仓库对比。

## 对 Claude 的预期 {#what-to-expect-from-claude}

不保证智能体的行为：该技能只是文本，智能体能否完成一次可运行的流程，只靠一次人工演示来证明，而不是自动化测试。

运行 Claude 编写的代码之前请先阅读，就像对待任何代码一样。

## 延伸阅读 {#further-reading}

- [方言与提供程序](dialects-and-providers.html)说明 Craticula 为哪些数据库编译，以及它们有何不同。
- [限制](limits.html)列出对请求大小和复杂度的上限。
- [安全模型](safety-model.html)列出 Craticula 保护什么、不保护什么。
- [C# 快速入门](quickstart-csharp.html)演示手动完成的相同步骤。
