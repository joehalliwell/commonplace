# Commonplace handbook

How commonplace behaves, across commands. Options and flags are in each
command's `--help`; [MANIFESTO.md](../MANIFESTO.md) says why it is built the way
it is.

## Layout

```
~/commonplace/
├── chats/                    # AI conversations (fetched or imported)
│   ├── claude/2026/06/2026-06-28-conversation-title.md
│   ├── chatgpt/2026/06/2026-06-28-conversation-title.md
│   ├── claude-code/2026/06/2026-06-28-session-title.md
│   ├── claude-tasks/2026/06/2026-06-28-run-title.md
│   ├── gemini/                       # fetched from gemini.google.com
│   └── gemini-takeout/               # imported from Google Takeout
├── memory/                   # agent memory, mirrored from each agent
│   ├── claude/
│   ├── chatgpt/
│   └── gemini/saved-info.md
├── journal/2026/06/2026-06-28.md     # daily entries
├── notes/                    # Manual notes and thoughts
├── index.md                  # what each top-level folder is for (seeded by init)
└── .commonplace/             # config, attachments, and the search index
```

Paths are meant to be read: underneath, a commonplace is a graph of
conversations, notes, links and provenance, laid out as a tree you can browse
like an outline. So a file is named for its date and title, never an id. Two
same-day chats with the same title become `…-title.md` and `…-title-2.md`, and
a chat keeps the path it first landed at even if it's retitled later, so links
and marginalia to it keep working.

Journal entries live at `journal/{year}/{month}/{date}.md`. Saving and exiting
the editor commits the entry; leaving it unchanged does nothing.

Every command that writes commits what it wrote: the commit includes only the
files the command wrote, and runs your git hooks, so if a hook reformats them,
the reformatted version is committed.

## Fetching

`fetch` is the main way in: it pulls new conversations straight from the
vendor, no export request or download to wait for.

`fetch` reads your logged-in session cookies from Chrome — log in once in the
browser and the session lasts several weeks (Claude) or a few days (Gemini,
with auto-refresh). The incremental cursor is derived from git history (last
commit touching the source's directory), so subsequent runs only pull what was
updated since the previous fetch.

The three chat sources — `claude`, `gemini`, `chatgpt` — land in
`chats/claude/`, `chats/gemini/` and `chats/chatgpt/`. Gemini's fetcher gets
per-turn timestamps, Gem personas and thought traces, which the Takeout export
doesn't have. Claude's gets slightly less than the manual export: the endpoint
strips `<antThinking>` blocks server-side (issue #6).

`claude-tasks` fetches the runs of your claude.ai scheduled tasks, which
claude.ai keeps apart from your chats. Each run lands as a chat in
`chats/claude-tasks/`, titled by the first line of its output shaped like
`[AI] What happened`, which a task's prompt can ask for, or otherwise by the
task's name and the time it started; `task` in the frontmatter names the task,
and `failed: true` marks a run that ended in an error. It opens with what the
run produced; reply to it in claude.ai and the conversation follows on the next
fetch. The prompt and the steps behind the output stay in the wire archive, and
the task definitions are not fetched.

These are the vendors' internal endpoints — unofficial, and they change without
notice. If a fetcher breaks, fall back to [manual exports](#importing); if a
vendor starts rejecting you as a bot, see [`ua`](#configuration).

`claude-code` reads your Claude Code sessions from `~/.claude/projects/` (or
`$CLAUDE_CONFIG_DIR/projects/`), where Claude Code keeps them, so it needs no
browser session. Each session changed since the last fetch is captured whole,
with its subagents and the full output of long tool calls, and lands in
`chats/claude-code/`, titled by the title Claude Code gave it, else by your
first prompt. The note is what was said: your prompts, your answers to the
agent's questions, and the agent's prose, with each tool call as one line
naming the tool and its first argument. Tool output, thinking, subagent
transcripts and turns the harness wrote, such as a skill's prompt or a
command's output, stay in the capture but not the note. When Claude Code
resumes an interrupted response in a new session, which copies the old one's
history, only the new session gets a note. A capture holds
whatever its tools printed, and git keeps every capture, so a secret that ever
shows up in a session stays in your history.

### Mirrors

Four more sources mirror agent memory. `claude-memory` mirrors claude.ai's
file-based memory into `memory/claude/`, each file at the path claude.ai gives
it, titled with the name claude.ai displays. `chatgpt-memory` mirrors
ChatGPT's "about you" summary into `memory/chatgpt/about-you.md`, a heading per
section; ChatGPT generates that summary itself and regenerates it on every
fetch, redrawing its sections, so it changes without you editing anything. ChatGPT's saved memories, the
facts you asked it to remember, go beside them in `saved-memories.md`, one
bullet per memory, oldest first. `gemini-memory` mirrors Gemini's
[saved info](https://gemini.google.com/saved-info) into
`memory/gemini/saved-info.md`, one bullet per item, oldest first.
`claude-code-memory` mirrors the memory Claude Code keeps for each project into
`memory/claude-code/<project>/`, named for the project's folder (a clash takes
`-2`), titled by each memory's `name`, with what kind of memory it is under
`metadata.type`. Each is a
mirror rather than an import: a memory deleted upstream is deleted here on the
next fetch, and git history keeps what it used to say. Every mirrored file's
frontmatter leads with `type: Memory` and its `title`. Memory is materially
more personal than chat logs — think before syncing it to a remote, or leave it
out with `--source`.

`keep` mirrors Google Keep into `notes/keep/yyyy/mm/`, one file per note dated
by its creation: a title becomes the heading, an untitled note is named after
its first words, a checklist becomes `- [ ]` items, and Keep's labels become the
note's `tags` (so `ls --field tags` shows them beside marginalia tags). A note
keeps the path it was first captured at even if you retitle it in Keep, so its
marginalia stay attached; notes in Keep's trash are left out, and attachments
aren't captured yet. Like memory, the tree is a mirror, rewritten on each fetch,
so say things about a note in its marginalia rather than editing it there.

## Importing

`fetch` covers the chat agents and Claude Code. Import is for everything else:
historical archives, and conversations a fetcher can't reach (see the
`<antThinking>` caveat above). It takes a vendor export, a wire archive written
by `fetch`, or a directory, which it searches recursively.

The format is detected per file — Claude export, ChatGPT export, Gemini
Takeout, or wire archive — and files no importer claims are skipped. Chats belong to commonplace: re-importing a conversation
rewrites it in place, so annotate them in `notes/`, not in the chat itself.
Import refuses the repo's own `.commonplace/blobs`: to re-render chats from the
archives already stored there, run `commonplace doctor --render`. Each chat is
an [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
document (`type: Chat`) whose `resource` links back to the conversation where
the agent has a URL for it, so re-importing also brings older chats up to date.
Its `models` lists the models the conversation used, in order and as the vendor
names them (`gpt-4o`, `3 Pro`), and is absent where the source records none.

### Exporting from each vendor

**Claude**: [claude.ai](https://claude.ai) → profile icon (bottom left) →
**Settings** → **Data & Privacy** → **Export data**. You'll get an email with a
download link, usually within a few minutes.

**ChatGPT**: [chatgpt.com](https://chatgpt.com) → profile icon → **Settings** →
**Data controls** → **Export data** → confirm. The email can take up to 24
hours.

**Gemini**: [Google Takeout](https://takeout.google.com) → **Deselect all** →
select **My Activity** → **Multiple formats**, ensure HTML is selected → **All
activity data included**, select only **Assistant** → **Next step** → **Create
export**. Can take several hours.

Export links are temporary and typically expire after 7 days.

## Search and the index

Notes are indexed as they are committed, so the index is usually current.
Search is hybrid by default, combining semantic and keyword matching.

Results only ever point at notes the repository still holds: one deleted since
the last index run is hidden rather than quoted back at you, and `--deleted`
reaches it while it is still in the index. A note you have merely *edited* keeps
matching on its old text until the next index run — it is still there to open,
so a slightly stale quote beats losing the note from search in the meantime.

Embeddings are computed locally (fastembed,
`snowflake/snowflake-arctic-embed-xs`) — the model downloads on first use and
nothing leaves your machine. When the model changes, run
`commonplace index --rebuild`: it drops the old model's entries and re-embeds
everything. The index lives at `.commonplace/cache/index.db` and is not tracked
by git. Every `.md` file is indexed except those git ignores or that sit under a
dot-directory (`.commonplace/`, `.claude/`, …), which hold tool state, not
notes. Only a note's body is indexed, not its frontmatter. In a chat, only what
the user and the agent said is indexed: tool calls and their output, and
`System` turns, stay in the note but not the index.

Each index run also drops chunks for notes that have been deleted or edited
since they were indexed, so the index tracks the repository instead of
accumulating every version of everything.

## Naming notes

Commands that take a note name it as a wikilink would: its name, or its path
from the root. A glob names many; a name that matches more than one note is
refused with the candidates listed.

```bash
commonplace tag ideas revisit
commonplace tag /chats/gemini/2026/05/2026-05-03-tea hidden
commonplace tag '/chats/claude-tasks/**' scheduled
```

`resolve` gives a note's path by the same names, for other tools:
`$EDITOR "$(commonplace resolve ideas)"`.

## Marginalia: tags and links

Tags live in the note's marginalia, a file at the note's own path under
`.commonplace/marginalia/`, not in the note itself. So any note can be tagged,
including chats and memory that the next fetch rewrites. Tagging commits as you,
not as the bot.

`hidden` is the one tag commonplace acts on: a hidden note stays in the
repository but is left out of `search` and `ls` (and so out of what skills
gather), unless you pass `--hidden`. `ls --field tags` shows marginalia tags
after a note's own.

A link's target can be a note, a heading, or a phrase quoted from the note, and
the rest of the line says why:

```bash
commonplace link /chats/gemini/2026/05/2026-05-03-tea "ideas#Tea house" filed as the tea house idea
commonplace link ideas '2026-11-02#"by the river"'
```

A link is a dated line in the first note's marginalia, with the target written
from the root (`- 2026-11-02 [[/notes/ideas#Tea house]] filed as …`), so a later
note of the same name can't make it ambiguous. Any wikilink you write in
marginalia by hand counts as a link too, unless it is quoted as code.

`show` gathers what other commands record about a note: its title and type, its
own tags and its marginalia tags, its links both ways (from marginalia and from
notes' own text), the commentary in its marginalia, its git history, and
whether its current version is in the search index. The record is about the
note, not the note itself.

`ls` builds a folder's listing from frontmatter each time it runs, so nothing in
the repository needs regenerating when a note changes.

## Sync and git

`sync` commits uncommitted changes and syncs with your git remote. For anything
sync doesn't cover, `commonplace git` runs git against the repo wherever you
happen to be, e.g. `commonplace git log --oneline -10`.

## Doctor

Each operation runs in turn under its own heading, and a closing line totals
what was fixed and what needs a look.

The scaffolding operation restores and commits any scaffolding that has gone
missing (`.gitignore`, `.claude/settings.json`, `.commonplace/config.toml`, the
root `index.md`, and the mdformat config in `.pre-commit-config.yaml` and
`.mdformat.toml`, which keeps wikilinks from being escaped, and a `.gitkeep` in
each top-level folder the root index links) and diffs the managed files against
the templates `init` currently writes. Run it after upgrading commonplace to see
what an older repo is missing. It only reports — applying the diff is up to you.
The root `index.md` and the config file are yours once seeded, so they are never
diffed.

The marginalia operation looks after tags and links whose note has moved. After
a plain `git mv`, the marginalia are left at the old path; doctor follows git's
rename detection and moves them to the note's new path. Marginalia whose note
was deleted are kept, as the record of what you made of it, and listed. Links in
marginalia whose note, heading or phrase has gone are reported.

It also checks that links land somewhere. Every reference your own markdown
makes into the repository is followed: inline and reference-style links,
images, wikilinks, raw HTML `href`/`src`, and the paths that topics list as
their `sources`. Anything that no longer resolves is reported with the file and
line it was written on, and — since a rename is what most breakage turns out to
be — where a file of that name lives now:

```
topics/art.md: 6 links that go nowhere
  line 12: notes/art-in-the-age-of-mechanical-creativity.md (no such file) — same name at notes/projects/art-in-the-age-of-mechanical-creativity.md
```

External URLs are not checked: that needs the network, and a slow, flaky check
is one you stop running. Neither is `chats/**` — a transcript quotes whatever
the model or you happened to write, so a link inside one is content, not a
claim about your repo. Chats are link targets, never link sources.

A link resolves the way GitHub resolves it: relative to the file it is written
in, or, with a leading `/`, relative to the repository root. Prefer the leading
`/` for links between top-level folders — `/journal/2024/01/2024-01-01.md`
reads the same from anywhere, where `../../journal/…` depends on where you wrote
it. Editors mostly agree: VS Code resolves `/` from the folder you opened, so
open the repository itself rather than a parent; Obsidian reportedly resolves it
from the vault root. Wikilinks name a note rather than a place, so `[[note]]`
and `[[folder/note]]` resolve to any note whose path ends that way.

## Claude Code skills

`init` writes a `.claude/settings.json` that registers this repo's plugin
marketplace, so Claude Code sees the skills when you open your commonplace.

| Skill                       | What it does                                                       |
| --------------------------- | ------------------------------------------------------------------ |
| `/synthesize [topic]`       | gather and distil a topic into `topics/{slug}.md`                  |
| `/resonate <slug> <slug> …` | surface interference patterns between synthesized topics           |
| `/rake`                     | surface unmade ideas, todos and projects for you to file           |
| `/project <sketch>`         | draft, or review and update, `notes/projects/{slug}.md`            |
| `/dream`                    | the agent dreams from random fragments, then reflects on the dream |

Artefacts have no dated filenames — git is the versioning layer, and repeat runs
update them in place. Everything under `topics/` is an
[OKF v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
concept document, recording its sources, the release that wrote it, and who
approved it.

Each skill works in a git worktree, so a run lands on your branch whole or not
at all. Before starting it asks what to do with any uncommitted files
(`commonplace sync` them, leave them, or cancel). Once you approve its output,
it fast-forwards your branch, removes the worktree and re-indexes, without
asking again. It never pushes; if your branch moved during the run, it stops and
leaves the worktree for you.

At the end of a run, a skill may write an entry of its own in
`agent-journal/{agent}/`, committed separately. Those entries are never treated
as evidence of your thinking.

## Configuration

The defaults are meant to work untouched. To change one, set it in a TOML file
or in an environment variable named after it, upper-cased with a `COMMONPLACE_`
prefix — e.g. `COMMONPLACE_EDITOR="code --wait"`. Each source overrides the ones
below it:

1. environment variables
1. `.commonplace/config.toml` in your commonplace (seeded by `init`)
1. `~/.config/commonplace/config.toml` (the platform config dir)
1. the defaults below

`root` is the exception: it says where the per-repo file is, so it can only come
from `COMMONPLACE_ROOT`. An unknown key in either file is an error, so a typo
can't silently do nothing.

`commonplace config` prints the settings in effect once every source is merged,
as TOML you can paste into a config file; `commonplace config user` prints just
that one value.

| Setting      | Default                     | Purpose                                    |
| ------------ | --------------------------- | ------------------------------------------ |
| `root`       | platform data dir           | where your commonplace lives               |
| `user`       | your login name, titlecased | how you're named in imported conversations |
| `editor`     | `$EDITOR`, else `vim`       | editor used by `commonplace journal`       |
| `wrap`       | `80`                        | target line length for written markdown    |
| `auto_index` | `true`                      | index new notes as they're committed       |
| `ua`         | a current Chrome UA         | User-Agent sent by fetchers                |

`ua` is the one worth knowing about: every vendor fronts its internal API with a
bot check that a stale User-Agent fails, so if fetches start getting blocked,
copy `navigator.userAgent` from your browser's console and set `COMMONPLACE_UA`
(or `ua`) to it — no need to wait for a release.

## Upgrading

What to do by hand when a release needs it. After any upgrade, run
`commonplace doctor` to see what scaffolding an older repo is missing.

**0.9.1**: a Claude Code session resumed in another no longer gets a note of its
own. Any fetched before stay, each a short duplicate of a note with the same
title; delete them by hand.

**0.9.0**: a Claude Code note keeps only what was said, with each tool call as
one line, so notes are about a sixth of their old size. Run
`commonplace doctor --render` to re-render the ones you have.

**0.8.0**: new archives are xz-compressed (`.jsonl.xz`), and an earlier release
can't read them, so upgrade commonplace on every machine that syncs your
commonplace. Archives stored before stay gzip and still read.

**0.6.0**: a chat's index holds only what was said, and a heading inside a code
block no longer splits a note into sections. An existing index keeps its old
chunks until you run `commonplace index --rebuild`.

**0.4.0**: Claude Code sessions arrive with `fetch`, and `import` no longer reads
`.jsonl` session logs, so drop `commonplace import ~/.claude/projects/` from your
routine. A session you imported before keeps its note and its path; the next
fetch brings it up to date.

**0.3.4**: blobs are plain git objects. A repo made earlier has a
`.gitattributes` routing `.commonplace/blobs` through Git LFS, which `doctor` no
longer manages; delete it and commit.

**0.0.6**: if you previously imported Gemini history from Takeout, move it aside
before the first `fetch --source gemini`. The fetcher owns `chats/gemini/`, and
the Takeout importer now writes to `chats/gemini-takeout/`:

```bash
commonplace git mv chats/gemini chats/gemini-takeout
commonplace git commit -m "Migrate Takeout Gemini imports to gemini-takeout path"
```
