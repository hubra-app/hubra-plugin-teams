import { apiFetch } from '@hubra/plugin-sdk'

export interface Options {
  can: { teams: boolean; matches: boolean }
  memberId: number
  groups?: { id: number; name: string; type: string }[]
}

export type Answer = 'yes' | 'maybe' | 'no'
export type Counts = Record<Answer, number>

export interface Match {
  id: number
  teamId: number
  opponent: string
  home: boolean | null
  startsAt: string
  meetAt: string | null
  location: string | null
  competition: string | null
  notes: string | null
  cancelled: boolean
  scoreUs: number | null
  scoreThem: number | null
  fromFeed: boolean
  lineupPublished: boolean
  counts: Counts
  myAnswer: Answer | null
  picked: boolean
}

export interface Person {
  memberId: number
  name: string
}

export interface MatchDetail extends Match {
  teamName: string
  coach: boolean
  inside: boolean
  answers?: (Person & { answer: Answer; note: string | null })[]
  unanswered?: Person[]
  lineup?: (Person & { role: 'starter' | 'sub'; position: string | null })[]
  rides?: {
    id: number
    driverId: number
    driver: string
    seats: number
    fromPlace: string | null
    departs: string | null
    note: string | null
    riders: Person[]
    mine: boolean
  }[]
}

export interface Team {
  id: number
  groupId: number
  name: string
  color: string | null
  players: number
  mine: boolean
  coach: boolean
  homeLocation: string | null
  inCalendar: boolean
  hasFeed: boolean
  next: Match | null
  feedUrl?: string | null
  feedName?: string | null
  feedSyncedAt?: string | null
  feedError?: string | null
}

const BASE = '/app/teams'
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const QK = {
  all: ['teams'] as const,
  options: ['teams', 'options'] as const,
  teams: ['teams', 'list'] as const,
  matches: (teamId: number, past: boolean) => ['teams', 'matches', teamId, past] as const,
  match: (id: number) => ['teams', 'match', id] as const,
}

export const getOptions = () => apiFetch<Options>(`${BASE}/options`)
export const listTeams = () => apiFetch<Team[]>(`${BASE}/teams`)
export const saveTeam = (body: Record<string, unknown>, id?: number) =>
  apiFetch<Team>(id ? `${BASE}/teams/${id}` : `${BASE}/teams`, json(id ? 'PATCH' : 'POST', body))
export const deleteTeam = (id: number) => apiFetch<void>(`${BASE}/teams/${id}`, { method: 'DELETE' })
export const syncTeam = (id: number) =>
  apiFetch<{ added: number; updated: number; cancelled: number }>(`${BASE}/teams/${id}/sync`, json('POST', {}))
export const listMatches = (teamId: number, past = false) =>
  apiFetch<Match[]>(`${BASE}/teams/${teamId}/matches${past ? '?past=1' : ''}`)
export const createMatch = (teamId: number, body: Record<string, unknown>) =>
  apiFetch<Match>(`${BASE}/teams/${teamId}/matches`, json('POST', body))
export const getMatch = (id: number) => apiFetch<MatchDetail>(`${BASE}/matches/${id}`)
export const updateMatch = (id: number, body: Record<string, unknown>) => apiFetch<Match>(`${BASE}/matches/${id}`, json('PATCH', body))
export const deleteMatch = (id: number) => apiFetch<void>(`${BASE}/matches/${id}`, { method: 'DELETE' })
export const answerMatch = (id: number, answer: Answer, note?: string | null) =>
  apiFetch<{ answer: Answer; counts: Counts }>(`${BASE}/matches/${id}/answer`, json('PUT', { answer, note }))
export const saveLineup = (id: number, picks: { memberId: number; role: string; position?: string | null }[], publish?: boolean) =>
  apiFetch<MatchDetail>(`${BASE}/matches/${id}/lineup`, json('PUT', { picks, publish }))
export const offerRide = (id: number, body: Record<string, unknown>) => apiFetch<MatchDetail>(`${BASE}/matches/${id}/rides`, json('POST', body))
export const withdrawRide = (id: number) => apiFetch<void>(`${BASE}/rides/${id}`, { method: 'DELETE' })
export const takeSeat = (id: number) => apiFetch<MatchDetail>(`${BASE}/rides/${id}/seat`, { method: 'PUT' })
export const leaveSeat = (id: number) => apiFetch<MatchDetail>(`${BASE}/rides/${id}/seat`, { method: 'DELETE' })

export function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

export function parseLocal(value: string) {
  const [day, time = '00:00'] = value.split('T')
  const [y, m, d] = day.split('-').map(Number)
  const [h, min] = time.split(':').map(Number)
  return new Date(y, m - 1, d, h, min)
}

export const hhmm = (value: string | null) => (value ? value.slice(11, 16) : '')

export function dayLabel(value: string, locale: string) {
  return parseLocal(value).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })
}
