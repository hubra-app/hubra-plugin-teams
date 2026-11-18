import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Anchor, Badge, Button, Group, NumberInput, Paper, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconArrowLeft, IconCar, IconClock, IconEdit, IconMapPin, IconPlus, IconTrash } from '@tabler/icons-react'
import { ConfirmModal, ErrorBanner, Field, LoadingSpinner, Modal, PageHead, TimeField, useT } from '@hubra/plugin-sdk'
import {
  QK,
  deleteMatch,
  errorText,
  getMatch,
  getOptions,
  hhmm,
  leaveSeat,
  offerRide,
  saveLineup,
  takeSeat,
  withdrawRide,
  type Answer,
  type MatchDetail,
} from './api'
import { useAction } from './common'
import { AnswerButtons, Counts, HomeBadge, answerColor, when } from './parts'
import { MatchModal } from './TeamScreen'

export function MatchScreen() {
  const { t, i18n } = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = Number(useParams().id)
  const match = useQuery({ queryKey: QK.match(id), queryFn: () => getMatch(id) })
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const { run } = useAction()
  const locale = i18n.language?.startsWith('de') ? 'de-CH' : 'en-GB'

  if (match.error) return <ErrorBanner message={errorText(match.error)} onRetry={() => match.refetch()} />
  if (match.isLoading || !match.data) return <LoadingSpinner />
  const m = match.data
  const result = m.scoreUs !== null && m.scoreThem !== null

  return (
    <>
      <PageHead
        back={
          <Anchor component="button" size="sm" onClick={() => navigate(`/app/teams/${m.teamId}`)}>
            <Group gap={4}>
              <IconArrowLeft size={14} /> {m.teamName}
            </Group>
          </Anchor>
        }
        title={m.home === false ? `${m.opponent} – ${m.teamName}` : `${m.teamName} – ${m.opponent}`}
        actions={
          m.coach ? (
            <Group gap="xs">
              <Button variant="default" leftSection={<IconEdit size={16} />} onClick={() => setEditing(true)}>
                {t('teams.editMatch')}
              </Button>
              {!m.fromFeed && (
                <Button variant="subtle" color="red" leftSection={<IconTrash size={16} />} onClick={() => setDeleting(true)}>
                  {t('teams.delete')}
                </Button>
              )}
            </Group>
          ) : undefined
        }
      />
      <Stack gap="md">
        <Paper withBorder radius="md" p="md">
          <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
            <Stack gap={4}>
              <Group gap="xs">
                <HomeBadge home={m.home} />
                {m.competition && (
                  <Badge size="sm" variant="light" color="gray" style={{ textTransform: 'none' }}>
                    {m.competition}
                  </Badge>
                )}
                {m.cancelled && (
                  <Badge size="sm" variant="light" color="red" style={{ textTransform: 'none' }}>
                    {t('teams.cancelled')}
                  </Badge>
                )}
              </Group>
              <Group gap={6}>
                <IconClock size={16} />
                <Text fw={600}>{when(m, locale)}</Text>
                {m.meetAt && (
                  <Text c="dimmed" size="sm">
                    · {t('teams.meetAt', { time: hhmm(m.meetAt) })}
                  </Text>
                )}
              </Group>
              {m.location && (
                <Group gap={6} wrap="nowrap">
                  <IconMapPin size={16} />
                  <Anchor href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(m.location)}`} target="_blank" rel="noreferrer">
                    {m.location}
                  </Anchor>
                </Group>
              )}
              {m.notes && (
                <Text size="sm" mt={4} style={{ whiteSpace: 'pre-wrap' }}>
                  {m.notes}
                </Text>
              )}
            </Stack>
            {result ? (
              <Title order={2}>
                {m.scoreUs}:{m.scoreThem}
              </Title>
            ) : (
              m.inside && (
                <Stack gap={6} align="flex-start" maw="100%">
                  <Text size="sm" c="dimmed">
                    {t('teams.areYouIn')}
                  </Text>
                  <AnswerButtons match={m} size="sm" />
                </Stack>
              )
            )}
          </Group>
        </Paper>
        {m.inside && (
          <>
            <Availability m={m} />
            {(m.coach || m.lineup) && <Lineup m={m} />}
            <Rides m={m} />
          </>
        )}
      </Stack>
      {editing && <MatchModal teamId={m.teamId} match={m} onClose={() => setEditing(false)} />}
      <ConfirmModal
        open={deleting}
        title={t('teams.deleteMatchTitle')}
        body={m.opponent}
        confirmLabel={t('teams.delete')}
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          setDeleting(false)
          if (await run(() => deleteMatch(m.id))) {
            qc.invalidateQueries({ queryKey: QK.all })
            navigate(`/app/teams/${m.teamId}`)
          }
        }}
      />
    </>
  )
}

function Section({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="sm" wrap="wrap">
        <Text fw={700}>{title}</Text>
        {extra}
      </Group>
      {children}
    </Paper>
  )
}

function Availability({ m }: { m: MatchDetail }) {
  const { t } = useT()
  const groups: { key: Answer | 'open'; people: { name: string; note?: string | null }[] }[] = [
    ...(['yes', 'maybe', 'no'] as Answer[]).map((a) => ({ key: a, people: (m.answers ?? []).filter((x) => x.answer === a) })),
    { key: 'open', people: m.unanswered ?? [] },
  ]
  return (
    <Section title={t('teams.availability')} extra={<Counts match={m} />}>
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
        {groups.map((g) => (
          <Stack key={g.key} gap={4}>
            <Text size="sm" fw={600} c={g.key === 'open' ? 'dimmed' : answerColor(g.key)}>
              {g.key === 'open' ? t('teams.noAnswer') : t(`teams.answer.${g.key}`)} ({g.people.length})
            </Text>
            {g.people.map((p) => (
              <Text key={p.name} size="sm" lh={1.3}>
                {p.name}
                {p.note ? (
                  <Text span size="xs" c="dimmed">
                    {' '}
                    · {p.note}
                  </Text>
                ) : null}
              </Text>
            ))}
          </Stack>
        ))}
      </SimpleGrid>
    </Section>
  )
}

type Role = 'starter' | 'sub' | 'out'

function Lineup({ m }: { m: MatchDetail }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [draft, setDraft] = useState<Record<number, { role: Role; position: string }>>({})
  useEffect(() => {
    const next: Record<number, { role: Role; position: string }> = {}
    for (const p of m.lineup ?? []) next[p.memberId] = { role: p.role, position: p.position ?? '' }
    setDraft(next)
  }, [m.lineup])

  if (!m.coach) {
    const starters = (m.lineup ?? []).filter((p) => p.role === 'starter')
    const subs = (m.lineup ?? []).filter((p) => p.role === 'sub')
    return (
      <Section title={t('teams.lineup')}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {[
            { label: t('teams.starters'), list: starters },
            { label: t('teams.subs'), list: subs },
          ].map((col) => (
            <Stack key={col.label} gap={4}>
              <Text size="sm" fw={600} c="dimmed">
                {col.label}
              </Text>
              {col.list.map((p) => (
                <Text key={p.memberId} size="sm">
                  {p.name}
                  {p.position ? (
                    <Text span c="dimmed">
                      {' '}
                      · {p.position}
                    </Text>
                  ) : null}
                </Text>
              ))}
            </Stack>
          ))}
        </SimpleGrid>
      </Section>
    )
  }

  const order: Record<string, number> = { yes: 0, maybe: 1, open: 2, no: 3 }
  const people = [
    ...(m.answers ?? []).map((a) => ({ memberId: a.memberId, name: a.name, answer: a.answer as string })),
    ...(m.unanswered ?? []).map((u) => ({ ...u, answer: 'open' })),
  ].sort((a, b) => order[a.answer] - order[b.answer] || a.name.localeCompare(b.name))
  const picks = () =>
    Object.entries(draft)
      .filter(([, v]) => v.role !== 'out')
      .sort(([, a], [, b]) => (a.role === b.role ? 0 : a.role === 'starter' ? -1 : 1))
      .map(([memberId, v]) => ({ memberId: Number(memberId), role: v.role, position: v.position || null }))
  const save = async (publish?: boolean) => {
    if (await run(() => saveLineup(m.id, picks(), publish), publish ? t('teams.lineupPublished') : t('teams.saved')))
      qc.invalidateQueries({ queryKey: QK.all })
  }
  const starters = Object.values(draft).filter((v) => v.role === 'starter').length

  return (
    <Section
      title={t('teams.lineup')}
      extra={
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            {t('teams.startersCount', { count: starters })}
          </Text>
          {m.lineupPublished ? (
            <Badge variant="light" color="green" style={{ textTransform: 'none' }}>
              {t('teams.published')}
            </Badge>
          ) : (
            <Badge variant="light" color="gray" style={{ textTransform: 'none' }}>
              {t('teams.draft')}
            </Badge>
          )}
        </Group>
      }
    >
      <Stack gap={6}>
        {people.map((p) => {
          const v = draft[p.memberId] ?? { role: 'out' as Role, position: '' }
          const set = (patch: Partial<{ role: Role; position: string }>) => setDraft({ ...draft, [p.memberId]: { ...v, ...patch } })
          return (
            <Stack key={p.memberId} gap={4}>
              <Group wrap="nowrap" gap="sm">
                <Badge size="xs" circle color={p.answer === 'open' ? 'gray' : answerColor(p.answer as Answer)} variant="filled" style={{ flexShrink: 0 }}>
                  {' '}
                </Badge>
                <Text size="sm" style={{ flex: 1, minWidth: 0 }} truncate>
                  {p.name}
                </Text>
                {v.role !== 'out' && (
                  <TextInput
                    visibleFrom="sm"
                    size="xs"
                    w={130}
                    aria-label={t('teams.position')}
                    placeholder={t('teams.position')}
                    value={v.position}
                    onChange={(e) => set({ position: e.currentTarget.value })}
                  />
                )}
                <SegmentedControl
                  size="xs"
                  value={v.role}
                  onChange={(r) => set({ role: r as Role })}
                  data={[
                    { value: 'out', label: '–' },
                    { value: 'starter', label: t('teams.starter') },
                    { value: 'sub', label: t('teams.sub') },
                  ]}
                />
              </Group>
              {v.role !== 'out' && (
                <TextInput
                  hiddenFrom="sm"
                  size="xs"
                  ml={26}
                  aria-label={t('teams.position')}
                  placeholder={t('teams.position')}
                  value={v.position}
                  onChange={(e) => set({ position: e.currentTarget.value })}
                />
              )}
            </Stack>
          )
        })}
      </Stack>
      <Group justify="flex-end" mt="md" gap="xs">
        <Button variant="default" loading={busy} onClick={() => save(m.lineupPublished ? true : undefined)}>
          {t('teams.saveLineup')}
        </Button>
        {!m.lineupPublished && (
          <Button loading={busy} onClick={() => save(true)}>
            {t('teams.publish')}
          </Button>
        )}
      </Group>
    </Section>
  )
}

function Rides({ m }: { m: MatchDetail }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [offering, setOffering] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })
  const driving = (m.rides ?? []).some((r) => r.mine)

  return (
    <Section
      title={t('teams.rides')}
      extra={
        !driving && !m.cancelled ? (
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setOffering(true)}>
            {t('teams.offerRide')}
          </Button>
        ) : undefined
      }
    >
      {!m.rides?.length ? (
        <Text size="sm" c="dimmed">
          {t('teams.noRides')}
        </Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {m.rides.map((r) => {
            const free = r.seats - r.riders.length
            return (
              <RideCard
                key={r.id}
                ride={r}
                free={free}
                busy={busy}
                onTake={async () => (await run(() => takeSeat(r.id))) && refresh()}
                onLeave={async () => (await run(() => leaveSeat(r.id))) && refresh()}
                onWithdraw={async () => (await run(() => withdrawRide(r.id))) && refresh()}
                canWithdraw={r.mine || m.coach}
              />
            )
          })}
        </SimpleGrid>
      )}
      {offering && <RideModal matchId={m.id} onClose={() => setOffering(false)} />}
    </Section>
  )
}

function RideCard({
  ride,
  free,
  busy,
  onTake,
  onLeave,
  onWithdraw,
  canWithdraw,
}: {
  ride: NonNullable<MatchDetail['rides']>[number]
  free: number
  busy: boolean
  onTake: () => void
  onLeave: () => void
  onWithdraw: () => void
  canWithdraw: boolean
}) {
  const { t } = useT()
  const { data: me } = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const aboard = !!me && ride.riders.some((x) => x.memberId === me.memberId)
  return (
    <Paper withBorder radius="md" p="sm">
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <IconCar size={18} />
          <div style={{ minWidth: 0 }}>
            <Text fw={600} truncate>
              {ride.driver}
            </Text>
            <Text size="xs" c="dimmed">
              {[ride.fromPlace, ride.departs ? t('teams.departs', { time: ride.departs }) : null].filter(Boolean).join(' · ')}
            </Text>
          </div>
        </Group>
        <Badge variant="light" color={free > 0 ? 'green' : 'gray'} style={{ textTransform: 'none', flexShrink: 0 }}>
          {t('teams.seatsFree', { count: free })}
        </Badge>
      </Group>
      {ride.note && (
        <Text size="sm" mt={6}>
          {ride.note}
        </Text>
      )}
      {ride.riders.length > 0 && (
        <Text size="sm" c="dimmed" mt={6}>
          {t('teams.riders', { names: ride.riders.map((x) => x.name).join(', ') })}
        </Text>
      )}
      <Group gap="xs" mt="sm">
        {!ride.mine &&
          (aboard ? (
            <Button size="xs" variant="default" loading={busy} onClick={onLeave}>
              {t('teams.leaveSeat')}
            </Button>
          ) : (
            free > 0 && (
              <Button size="xs" loading={busy} onClick={onTake}>
                {t('teams.takeSeat')}
              </Button>
            )
          ))}
        {canWithdraw && (
          <Button size="xs" variant="subtle" color="red" loading={busy} onClick={onWithdraw}>
            {t('teams.withdrawRide')}
          </Button>
        )}
      </Group>
    </Paper>
  )
}

function RideModal({ matchId, onClose }: { matchId: number; onClose: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [seats, setSeats] = useState<number | string>(3)
  const [fromPlace, setFromPlace] = useState('')
  const [departs, setDeparts] = useState('')
  const [note, setNote] = useState('')
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => offerRide(matchId, { seats, fromPlace: fromPlace || null, departs: departs || null, note: note || null }), t('teams.rideOffered'))) {
      qc.invalidateQueries({ queryKey: QK.all })
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('teams.offerRide')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('teams.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!seats}>
            {t('teams.offer')}
          </Button>
        </>
      }
    >
      <Group grow align="flex-start">
        <Field label={t('teams.seats')}>
          <NumberInput value={seats} onChange={setSeats} min={1} max={60} data-autofocus />
        </Field>
        <Field label={t('teams.departsField')}>
          <TimeField value={departs} onChange={setDeparts} />
        </Field>
      </Group>
      <Field label={t('teams.fromPlace')}>
        <TextInput value={fromPlace} onChange={(e) => setFromPlace(e.currentTarget.value)} placeholder={t('teams.fromPlaceExample')} />
      </Field>
      <Field label={t('teams.rideNote')}>
        <TextInput value={note} onChange={(e) => setNote(e.currentTarget.value)} />
      </Field>
    </Modal>
  )
}
