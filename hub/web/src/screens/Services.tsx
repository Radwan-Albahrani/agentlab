import * as stylex from '@stylexjs/stylex';
import { useState, type ReactNode } from 'react';
import { useServices } from '../api/queries';
import type { Services as Data, Stack } from '../api/types';
import { Screen } from '../app/Screen';
import {
  ConfigLink,
  ContainerActions,
  ContainerRows,
  domainSub,
  HealthTag,
  readStatus,
  StackLead,
  StackName,
  WatcherPending,
} from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { plural } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { colors, font, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { LinkButton } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { Appear } from '../ui/motion';
import { PageHead, Stat } from '../ui/page';
import { Badge } from '../ui/status';

const styles = stylex.create({
  // the health panel: a verdict line, a number strip, and one square per container
  health: {
    display: 'grid',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    overflow: 'hidden',
    backgroundColor: colors.panel,
  },
  verdict: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    minWidth: 0,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  mark: {
    width: 28,
    height: 28,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.ok} 35%, ${colors.line})`,
    color: colors.ok,
    backgroundColor: colors.okSoft,
  },
  markBad: {
    borderColor: `color-mix(in srgb, ${colors.bad} 40%, ${colors.line})`,
    color: colors.bad,
    backgroundColor: colors.badSoft,
  },
  headline: { margin: 0, fontFamily: font.display, fontSize: text.xl, fontWeight: 600, lineHeight: 1.2 },
  sentence: { margin: 0, color: colors.muted, fontSize: text.md },
  strip: {
    display: 'grid',
    gridTemplateColumns: {
      default: 'repeat(3, minmax(120px, max-content)) minmax(0, 1fr)',
      [media.narrow]: 'repeat(3, minmax(0, 1fr))',
    },
    gap: 1,
    backgroundColor: colors.line,
  },
  // small multiples: a group of squares per stack, one square per container
  map: {
    gridColumn: { default: null, [media.narrow]: '1 / -1' },
    display: 'flex',
    flexWrap: 'wrap',
    alignContent: 'center',
    gap: space.lg,
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    backgroundColor: colors.panel,
  },
  mapGroup: { display: 'grid', gap: space.xxs, minWidth: 0 },
  mapLabel: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    maxWidth: 120,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  mapCells: { display: 'flex', gap: 2 },
  cell: {
    width: 12,
    height: 12,
    backgroundColor: colors.ok,
    opacity: { default: 0.8, ':hover': 1 },
    transitionProperty: 'opacity',
    transitionDuration: '120ms',
  },
  cellBad: { backgroundColor: colors.bad, opacity: 1 },
  // incidents: coral-edged, on top, with their actions in reach
  incident: {
    borderRadius: radius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.bad} 55%, ${colors.line})`,
    backgroundColor: colors.panel,
  },
  incidentHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    color: colors.bad,
    backgroundColor: colors.badSoft,
  },
  incidentStack: {
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: `color-mix(in srgb, ${colors.bad} 25%, ${colors.line})`,
  },
  incidentWho: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    paddingBlockStart: space.lg,
    paddingBlockEnd: space.xs,
    paddingInline: space.xxl,
  },
  incidentCount: { fontFamily: font.mono, fontSize: text.xs, color: colors.bad, fontVariantNumeric: 'tabular-nums' },
  // a domain: a mono label on a hairline rule, its stacks as cells of one grid under it
  group: { display: 'grid', gap: space.lg, minWidth: 0 },
  groupHead: { display: 'flex', alignItems: 'center', gap: space.md, flexWrap: 'wrap', minHeight: 30 },
  groupIcon: { display: 'flex', color: colors.faint },
  groupName: {
    margin: 0,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
  },
  groupSub: { fontSize: text.sm, color: colors.faint },
  groupRule: { flex: '1', minWidth: space.xxl, height: 1, backgroundColor: colors.line },
  // every cell rings itself with a hairline into the 1px gap, so neighbours share one line and empty slots stay clear
  tiles: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 272px), 1fr))',
    gap: 1,
    padding: 1,
  },
  tile: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
    backgroundColor: colors.panel,
    boxShadow: `0 0 0 1px ${colors.line}`,
  },
  tileOpen: { gridColumnStart: 1, gridColumnEnd: -1 },
  tileTop: {
    flex: '1',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    minWidth: 0,
  },
  tileText: { flex: '1', minWidth: 0 },
  tileName: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  tileSub: {
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  beacon: { width: 8, height: 8, flexShrink: 0, backgroundColor: colors.ok },
  tileFoot: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    flexWrap: 'wrap',
    paddingBlock: space.sm,
    paddingInline: space.xl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: colors.raised,
  },
  spacer: { flex: '1' },
  chips: { display: 'flex', gap: space.xxs, flexWrap: 'wrap', minWidth: 0 },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.muted,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.sunk,
  },
  chipDot: { width: 6, height: 6, backgroundColor: colors.ok },
  toggle: {
    appearance: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xxs,
    paddingBlock: space.xxs,
    paddingInline: space.sm,
    borderWidth: 0,
    borderRadius: radius.sm,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.muted, ':hover': colors.fg },
    fontSize: text.sm,
    fontWeight: 500,
    cursor: 'pointer',
    transitionProperty: 'background-color, color',
    transitionDuration: '120ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  caret: {
    display: 'flex',
    transitionProperty: 'transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
  },
  caretOpen: { transform: 'rotate(180deg)' },
  detail: { borderTopWidth: 1, borderTopStyle: 'solid', borderTopColor: colors.line },
});

export function Services() {
  const query = useServices();
  return (
    <Screen title="Services" query={query}>
      {(d) => <ServicesView d={d} />}
    </Screen>
  );
}

const isDown = (s: Stack) => s.containers.some((c) => !c.healthy);

function ServicesView({ d }: { d: Data }) {
  const canSee = useCanSee();
  const all = [...d.domains.flatMap((x) => x.stacks), ...d.other];
  const down = all.filter(isDown);
  const otherUp = d.other.filter((s) => !isDown(s));
  const containers = all.flatMap((s) => s.containers);
  const bad = containers.filter((c) => !c.healthy).length;
  return (
    <>
      <PageHead
        eyebrow={
          all.length
            ? `${plural(containers.length, 'container')} · ${plural(all.length, 'stack')} · ${bad ? `${bad} down` : 'all nominal'}`
            : 'cluster'
        }
        title="Services"
        sub="Every container the cluster runs, grouped by agent with its companions. Anything down rises to the top with its logs and a restart at hand."
        right={canSee('/config') ? <LinkButton label="Configs" icon="sliders" to="/config" /> : undefined}
      />
      {!all.length ? (
        <WatcherPending />
      ) : (
        <>
          {down.length > 0 && <Incidents stacks={down} />}
          <Health d={d} all={all} />
          {d.domains.map((x) => {
            const up = x.stacks.filter((s) => !isDown(s));
            if (!up.length) return null;
            return (
              <Group
                key={x.profile}
                profile={x.profile}
                title={x.profile}
                sub={domainSub(x.stacks.length)}
                right={<LinkButton label="Open" icon="arrow" variant="quiet" small to={`/agents/${x.profile}`} />}
              >
                {up.map((s) => (
                  <Tile key={s.id} stack={s} />
                ))}
              </Group>
            );
          })}
          {otherUp.length > 0 && (
            <Group title="Infrastructure" sub="the hub, its gateway and any other stacks on the server">
              {otherUp.map((s) => (
                <Tile key={s.id} stack={s} />
              ))}
            </Group>
          )}
        </>
      )}
    </>
  );
}

function Health({ d, all }: { d: Data; all: Stack[] }) {
  const containers = all.flatMap((s) => s.containers);
  const bad = containers.filter((c) => !c.healthy).length;
  const downStacks = all.filter(isDown).length;
  return (
    <section {...stylex.props(styles.health)} aria-label="Health">
      <div {...stylex.props(styles.verdict)}>
        <span {...stylex.props(styles.mark, bad > 0 && styles.markBad)}>
          <Icon name={bad ? 'alert' : 'check'} size={16} />
        </span>
        <div>
          <p {...stylex.props(styles.headline)}>{bad ? `${plural(bad, 'container')} down` : 'Everything is healthy'}</p>
          <p {...stylex.props(styles.sentence)}>
            {bad
              ? `${plural(downStacks, 'stack')} affected · the rest are running normally`
              : `${plural(containers.length, 'container')} in ${plural(all.length, 'stack')}, all answering their health checks`}
          </p>
        </div>
      </div>
      <div {...stylex.props(styles.strip)}>
        <Stat label="Healthy" value={containers.length - bad} of={`/ ${containers.length}`} tone={bad ? 'bad' : 'ok'} />
        <Stat label="Stacks" value={all.length} />
        <Stat label={d.domains.length === 1 ? 'Agent' : 'Agents'} value={d.domains.length} />
        <div {...stylex.props(styles.map)} aria-hidden="true">
          {all.map((s) => (
            <span key={s.id} {...stylex.props(styles.mapGroup)}>
              <span {...stylex.props(styles.mapLabel)}>{s.profile ?? s.label}</span>
              <span {...stylex.props(styles.mapCells)}>
                {s.containers.map((c) => (
                  <i
                    key={c.name}
                    title={`${s.label} · ${c.service} · ${c.status}`}
                    {...stylex.props(styles.cell, !c.healthy && styles.cellBad)}
                  />
                ))}
              </span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function Incidents({ stacks }: { stacks: Stack[] }) {
  return (
    <section {...stylex.props(styles.incident)} aria-label="Down">
      <div {...stylex.props(styles.incidentHead)}>
        <Icon name="alert" size={14} />
        {stacks.length === 1 ? 'One stack needs attention' : `${stacks.length} stacks need attention`}
      </div>
      {stacks.map((s, i) => {
        const bad = s.containers.filter((c) => !c.healthy).length;
        return (
          <Appear key={s.id} i={i}>
            <div {...stylex.props(hueTheme(s.profile), styles.incidentStack)}>
              <div {...stylex.props(styles.incidentWho)}>
                <StackLead stack={s} />
                <div {...stylex.props(styles.tileText)}>
                  <div>
                    <StackName stack={s} />
                  </div>
                  <div {...stylex.props(styles.incidentCount)}>
                    {bad} of {plural(s.containers.length, 'container')} down
                  </div>
                </div>
                <ConfigLink stack={s} />
              </div>
              <ContainerRows stack={s} />
            </div>
          </Appear>
        );
      })}
    </section>
  );
}

function Group({
  profile,
  title,
  sub,
  right,
  children,
}: {
  profile?: string;
  title: string;
  sub: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section {...stylex.props(styles.group)} aria-label={title}>
      <div {...stylex.props(styles.groupHead)}>
        {profile ? (
          <Badge name={profile} size="xs" />
        ) : (
          <span {...stylex.props(styles.groupIcon)}>
            <Icon name="layers" size={14} />
          </span>
        )}
        <h2 {...stylex.props(styles.groupName)}>{title}</h2>
        <span {...stylex.props(styles.groupSub)}>{sub}</span>
        <span {...stylex.props(styles.groupRule)} />
        {right}
      </div>
      <div {...stylex.props(styles.tiles)}>{children}</div>
    </section>
  );
}

/** A healthy stack, compact: one container shows its actions; several fold out into rows. */
function Tile({ stack: s }: { stack: Stack }) {
  const [open, setOpen] = useState(false);
  const only = s.containers.length === 1 ? s.containers[0] : undefined;
  const status = only ? readStatus(only) : null;
  return (
    <div {...stylex.props(hueTheme(s.profile), styles.tile, open && styles.tileOpen)}>
      <div {...stylex.props(styles.tileTop)}>
        <StackLead stack={s} />
        <div {...stylex.props(styles.tileText)}>
          <div {...stylex.props(styles.tileName)}>
            <StackName stack={s} />
          </div>
          <div {...stylex.props(styles.tileSub)}>
            {only && status ? (
              <>
                {status.uptime}
                <HealthTag c={only} />
              </>
            ) : (
              `${plural(s.containers.length, 'container')} · all healthy`
            )}
          </div>
        </div>
        <i {...stylex.props(styles.beacon)} title="Healthy" />
      </div>
      {only ? (
        <div {...stylex.props(styles.tileFoot)}>
          <ContainerActions stack={s} c={only} />
          <span {...stylex.props(styles.spacer)} />
          <ConfigLink stack={s} iconOnly />
        </div>
      ) : (
        <>
          <div {...stylex.props(styles.tileFoot)}>
            {!open && (
              <span {...stylex.props(styles.chips)}>
                {s.containers.map((c) => (
                  <span key={c.name} {...stylex.props(styles.chip)}>
                    <i {...stylex.props(styles.chipDot)} />
                    {c.service}
                  </span>
                ))}
              </span>
            )}
            <span {...stylex.props(styles.spacer)} />
            <ConfigLink stack={s} iconOnly />
            <button
              type="button"
              {...stylex.props(styles.toggle)}
              aria-expanded={open}
              onClick={() => {
                setOpen(!open);
              }}
            >
              {open ? 'Fold' : 'Containers'}
              <span {...stylex.props(styles.caret, open && styles.caretOpen)}>
                <Icon name="chevron" size={15} />
              </span>
            </button>
          </div>
          {open && (
            <div {...stylex.props(styles.detail)}>
              <ContainerRows stack={s} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
