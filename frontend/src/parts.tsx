import { useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Group, Paper, Stack, Text } from '@mantine/core'
import { IconCheck, IconQuestionMark, IconX } from '@tabler/icons-react'
import { useT } from '@hubra/plugin-sdk'
import { QK, answerMatch, dayLabel, hhmm, parseLocal, type Answer, type Match } from './api'
import { useAction } from './common'

const COLORS: Record<Answer, string> = { yes: 'green', maybe: 'yellow', no: 'red' }
const ICONS: Record<Answer, React.ReactNode> = {
  yes: <IconCheck size={14} />,
  maybe: <IconQuestionMark size={14} />,
  no: <IconX size={14} />,
}

export const answerColor = (a: Answer) => COLORS[a]

/** Yes / maybe / no for one match. */
export function AnswerButtons({ match, size = 'xs' }: { match: Match; size?: 'xs' | 'sm' }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const past = parseLocal(match.startsAt) < new Date()
  if (match.cancelled || past) return null
  return (
    <Group gap={6} wrap="wrap" onClick={(e) => e.stopPropagation()}>
      {(['yes', 'maybe', 'no'] as Answer[]).map((a) => (
        <Button
          key={a}
          size={size}
          radius="xl"
          color={COLORS[a]}
          variant={match.myAnswer === a ? 'filled' : 'light'}
          leftSection={ICONS[a]}
          disabled={busy}
          aria-pressed={match.myAnswer === a}
          onClick={async () => {
            if (await run(() => answerMatch(match.id, a))) qc.invalidateQueries({ queryKey: QK.all })
          }}
        >
          {t(`teams.answer.${a}`)}
        </Button>
      ))}
    </Group>
  )
}

export function HomeBadge({ home }: { home: boolean | null }) {
  const { t } = useT()
  if (home === null) return null
  return (
    <Badge size="sm" variant="light" color={home ? 'violet' : 'gray'} style={{ textTransform: 'none' }}>
      {home ? t('teams.home') : t('teams.away')}
    </Badge>
  )
}

export function Counts({ match }: { match: Match }) {
  const { t } = useT()
  return (
    <Group gap={8} wrap="nowrap">
      {(['yes', 'maybe', 'no'] as Answer[]).map((a) => (
        <Text key={a} size="xs" c={COLORS[a]} fw={600} title={t(`teams.answer.${a}`)}>
          {match.counts[a]} {t(`teams.answerShort.${a}`)}
        </Text>
      ))}
    </Group>
  )
}

/** One match in a list: the date block, the opponent, answers. */
export function MatchRow({ match, onOpen, inside }: { match: Match; onOpen: () => void; inside: boolean }) {
  const { t, i18n } = useT()
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'
  const d = parseLocal(match.startsAt)
  const result = match.scoreUs !== null && match.scoreThem !== null
  return (
    <Paper withBorder radius="md" p="sm" style={{ cursor: 'pointer', opacity: match.cancelled ? 0.6 : 1 }} onClick={onOpen}>
      <Group wrap="nowrap" align="center" gap="md">
        <Stack gap={0} align="center" w={52} style={{ flexShrink: 0 }}>
          <Text size="xs" c="dimmed" tt="uppercase">
            {d.toLocaleDateString(locale, { weekday: 'short' })}
          </Text>
          <Text fw={700} size="lg" lh={1.1}>
            {d.getDate()}
          </Text>
          <Text size="xs" c="dimmed">
            {d.toLocaleDateString(locale, { month: 'short' })}
          </Text>
        </Stack>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Group gap={6} wrap="nowrap">
            <Text fw={600} truncate td={match.cancelled ? 'line-through' : undefined}>
              {match.opponent}
            </Text>
            <HomeBadge home={match.home} />
            {match.cancelled && (
              <Badge size="sm" variant="light" color="red" style={{ textTransform: 'none' }}>
                {t('teams.cancelled')}
              </Badge>
            )}
            {match.picked && (
              <Badge size="sm" variant="filled" color="violet" style={{ textTransform: 'none' }}>
                {t('teams.youPlay')}
              </Badge>
            )}
          </Group>
          <Text size="sm" c="dimmed" truncate>
            {hhmm(match.startsAt)}
            {match.location ? ` · ${match.location}` : ''}
            {match.competition ? ` · ${match.competition}` : ''}
          </Text>
          {inside && !result && (
            <Group mt={6} gap="md" wrap="wrap">
              <AnswerButtons match={match} />
              <Counts match={match} />
            </Group>
          )}
        </div>
        {result && (
          <Text fw={700} size="lg" style={{ flexShrink: 0 }}>
            {match.scoreUs}:{match.scoreThem}
          </Text>
        )}
      </Group>
    </Paper>
  )
}

export function when(match: Match, locale: string) {
  return `${dayLabel(match.startsAt, locale)} · ${hhmm(match.startsAt)}`
}
