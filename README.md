# Teams

[![Test and release](https://github.com/hubra-app/hubra-plugin-teams/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/hubra-app/hubra-plugin-teams/actions/workflows/release.yml?query=branch%3Amain) [![Release](https://img.shields.io/github/v/release/hubra-app/hubra-plugin-teams)](https://github.com/hubra-app/hubra-plugin-teams/releases/latest) [![License: all rights reserved](https://img.shields.io/badge/license-all%20rights%20reserved-lightgrey)](LICENSE)

A plugin for [Hubra](https://hubra.club). Match days for team sports: fixtures from the league's calendar feed, who can play, the coach's line-up, and carpooling to away games.

**Version** 1.0.0 · **Works with** Hubra >=0.2,<1 · **Plugin id** `teams` · **Needs** the members and groups modules (and events, to show matches in the club calendar)

![Match](docs/screenshots/match.png)

## What it does

A team is one of the club's groups: its members are the players, and its
lead is the coach (as is anyone with `teams.matches.update`).

| Part | |
| --- | --- |
| Fixtures | The coach adds matches, or links the league's iCal calendar (webcal or https). Hubra reads it every hour: new matches come in, moved ones are updated, future ones that left the feed are marked called off. The team's name in the feed tells home from away. Matches can also show in the club calendar (Anlässe, category "competition"). |
| Availability | Players answer Dabei, Vielleicht or Nicht dabei, with an optional note, on the team list, the team page or the match. Three days before a match, those who haven't answered get a bell notification. |
| Line-up | The coach picks starters and substitutes with a position, saves a draft, then publishes it. Those picked get a notification and see "Du spielst" on the match. |
| Carpooling | A player offers seats with a meeting point and time; teammates take a seat (one per match). If the driver withdraws, the riders are told. |

Only public https hosts are fetched for feeds (`TEAMS_FEED_ALLOW_PRIVATE=1`
lifts that for a local test server); feeds are capped at 2 MB.

Permissions: `teams.teams.update` (set up teams and feeds),
`teams.matches.update` (coach every team). Every member sees the teams and
their fixtures; answers, line-ups and rides are for the team.

## Install

Platform admins install it from the Plugin catalogue in manage
(official Marketplace, <https://plugins.hubra.club/index.json>, signed with
the Hubra project key). Clubs then switch it on under Einstellungen → Module.

## Develop

Clone this repository into `plugins/teams` of a Hubra checkout. Its tests
then run with Hubra's (`cd app/backend && pytest ../../plugins/teams`), and
`npm run build:plugin` in `app/frontend` builds its frontend. The workflow
does the same against Hubra's `main` on every push and pull request.

## Releasing

Bump `version` in `plugin.yaml`, add a `## <version>` section to
`CHANGELOG.md` and merge. Then tag the merged commit on main and push the tag:

```sh
git switch main && git pull
git tag v<version> && git push origin v<version>
```

The workflow tests the plugin and builds its frontend, the `plugin-signing`
job signs it after your approval, and only then is the GitHub release
`v<version>` published, with `teams-<version>.zip` and its `.sha256` attached.
Files listed in `.releaseignore` stay out of the zip. Releases are immutable,
so a published version never changes: fix a bad one with a new version.

Source: <https://github.com/hubra-app/hubra-plugin-teams>
