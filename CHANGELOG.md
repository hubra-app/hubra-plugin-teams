# Teams

## Unreleased

- Date, date-and-time and time fields use Hubra's date pickers: dd.mm.yyyy, a calendar that starts on Monday and 24-hour times, whatever the browser language; typed dates like 1.2.26 work too. Needs Hubra 0.2.6 or later.

## 1.1.1

- German: gender forms read "Spieler/in", "Trainer/in", like the rest of Hubra; "z. B." with a space.
- Security: a fixture feed is downloaded from the address that was checked as public, so a calendar link can no longer reach the server's own network by answering DNS differently the second time (DNS rebinding). IPv6 forms of private IPv4 addresses (::ffff:, 2002::, NAT64) count as private too.
- A calendar link with an invalid port is refused with a message instead of failing the sync; a feed that repeats an event UID no longer stops the hourly sync of the club's other teams.
- Removed unused finance helpers (no more import of finance models).

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Mitglied Ansehen, Vorstand Bearbeiten. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.
- Dashboard widget **Nächste Spiele**: the next matches of the member's teams (or all teams), with time, place and their own answer.

## 1.0.0

First version: teams from the club's groups, fixtures from a league iCal
feed (hourly) or entered by the coach, mirrored into the club calendar,
availability with a reminder three days before, line-ups with a
notification, and carpooling.
