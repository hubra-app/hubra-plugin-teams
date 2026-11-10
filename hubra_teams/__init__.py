"""Teams: match days for team sports.

A team is one of the club's groups. Its members are the players; the
group's lead and anyone with ``teams.matches.update`` are its coaches.

- Fixtures: the coach adds matches, or the team follows the league's iCal
  feed and Hubra keeps them up to date every hour. Matches can also show in
  the club calendar (Anlässe).
- Availability: players answer yes, maybe or no; a reminder goes out three
  days before to those who haven't.
- Line-up: the coach picks starters and substitutes and publishes it; those
  picked get a notification.
- Carpooling: drivers offer seats, players take one.

Permissions:
    teams.teams.update     set up teams and their fixture feeds
    teams.matches.update   coach every team (a group lead coaches their own)
"""

from hubra.core.contracts import WidgetField, widget_contract
from hubra.core.modules import Blueprint, Module, NavItem, Schedule

module = Module(
    code="teams",
    # Access the standard roles get when a club first switches it on
    # (docs/roles.md in hubra-app/hubra).
    role_defaults={"member": "view", "board": "edit"},
    name="Teams",
    description="Match days: fixtures, availability, line-ups and carpooling",
    default_enabled=False,
    depends_on=("members", "groups"),
    blueprints=(Blueprint("hubra_teams.routes", "teams_bp", "/api/v1/app/teams"),),
    nav=(
        NavItem(
            "/app/teams",
            "shell.nav.teams",
            "shirt-sport",
            section="more",
            order=28,
        ),
    ),
    tasks=("hubra_teams.tasks",),
    schedule=(
        Schedule("teams-feeds-hourly", "hubra_teams.tasks.sync_feeds", 3600.0),
        Schedule("teams-reminders-daily", "hubra_teams.tasks.remind", 86400.0),
    ),
    tables=(
        "teams_teams",
        "teams_matches",
        "teams_answers",
        "teams_picks",
        "teams_rides",
        "teams_seats",
    ),
    # Dashboard widgets (hubra_teams/widgets.py).
    provides=(
        widget_contract(
            "teams.matches",
            "hubra_teams.widgets:matches",
            label="teams.widget.matches",
            description="teams.widget.matchesHint",
            size="m",
            view="list",
            fields=(
                WidgetField("mine", "teams.widget.mine", "switch", True),
                WidgetField("count", "teams.widget.count", "number", 5),
            ),
        ),
    ),
)
