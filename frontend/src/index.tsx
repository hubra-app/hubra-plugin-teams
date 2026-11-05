import { registerPlugin } from '@hubra/plugin-sdk'
import { IconShirtSport } from '@tabler/icons-react'
import { MatchScreen } from './MatchScreen'
import { TeamScreen } from './TeamScreen'
import { TeamsScreen } from './TeamsScreen'
import translations from './translations.json'

registerPlugin({
  id: 'teams',
  routes: [
    { path: 'teams', module: 'teams', component: TeamsScreen },
    { path: 'teams/matches/:id', module: 'teams', component: MatchScreen },
    { path: 'teams/:id', module: 'teams', component: TeamScreen },
  ],
  // The nav entry in hubra_teams/__init__.py names this icon.
  icons: { 'shirt-sport': IconShirtSport },
  translations,
})
