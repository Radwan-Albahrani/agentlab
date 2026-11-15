import * as stylex from '@stylexjs/stylex';
import { useDisplay } from '../api/queries';
import type { DisplayMode, DisplaySettings } from '../api/types';
import { Screen } from '../app/Screen';
import { colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Card } from '../ui/Card';
import { Segments, Switch } from '../ui/controls';
import { useAct } from '../ui/feedback';
import { Appear } from '../ui/motion';
import { PageHead, Section } from '../ui/page';
import { List, Row } from '../ui/Row';

const MODES: { value: DisplayMode; label: string }[] = [
  { value: 'show', label: 'Show' },
  { value: 'present', label: 'Hide while presenting' },
  { value: 'hide', label: 'Always hide' },
];

const GROUP_ICON: Record<string, string> = { Overview: 'home', Agents: 'agents', Companions: 'bot', System: 'sliders' };

// eye, a screen being shown, a crossed-out eye
const MARK: Record<DisplayMode, string> = {
  show: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM14.8 12a2.8 2.8 0 1 1-5.6 0 2.8 2.8 0 0 1 5.6 0z',
  present: 'M3.5 4.5h17v11.5h-17zM8.5 20.5h7M12 16v4.5',
  hide: 'M4 4l16 16M10.6 5.6Q11.3 5.5 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.7 3.4M6.6 6.6C4 8.4 2.5 12 2.5 12S6 18.5 12 18.5c1.8 0 3.4-.6 4.8-1.4M9.9 9.9a2.8 2.8 0 0 0 4.2 4.2',
};

const visible = (mode: DisplayMode, presenting: boolean) => mode === 'show' || (mode === 'present' && !presenting);

const styles = stylex.create({
  hero: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1fr) minmax(0, 1.1fr)', [media.narrow]: '1fr' },
    gap: space.huge,
    paddingBlock: { default: space.huge, [media.phone]: space.xxxl },
    paddingInline: { default: space.huge, [media.phone]: space.xxl },
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    transitionProperty: 'border-color, background-color',
    transitionDuration: '160ms',
  },
  // presenting changes what everyone sees: the whole panel turns amber-edged
  heroOn: {
    borderColor: `color-mix(in srgb, ${colors.accent} 55%, ${colors.line})`,
    backgroundColor: colors.accentSoft,
  },
  control: { display: 'grid', gap: space.lg, alignContent: 'start' },
  switchRow: { display: 'flex', alignItems: 'center', gap: space.lg },
  title: { margin: 0, fontFamily: font.display, fontSize: text.xxl, fontWeight: 600, lineHeight: 1.1 },
  state: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  stateOn: { color: colors.accent },
  explain: { margin: 0, color: colors.muted, fontSize: text.base, maxWidth: '52ch' },
  keys: { display: 'flex', alignItems: 'center', gap: space.xs, flexWrap: 'wrap', fontSize: text.sm, color: colors.faint },
  kbd: {
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 500,
    color: colors.fg,
    paddingBlock: 1,
    paddingInline: space.sm,
    borderRadius: radius.xs,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderBottomWidth: 2,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  // the preview: small multiples, one square per item, lit when it is on screen right now
  preview: {
    display: 'grid',
    gap: space.md,
    alignContent: 'start',
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.lg,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  previewHead: { display: 'flex', alignItems: 'baseline', gap: space.sm, flexWrap: 'wrap' },
  previewLabel: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  previewCount: {
    marginInlineStart: 'auto',
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.muted,
    fontVariantNumeric: 'tabular-nums',
  },
  lane: {
    display: 'grid',
    gridTemplateColumns: '96px minmax(0, 1fr) auto',
    gap: space.md,
    alignItems: 'center',
    fontSize: text.sm,
  },
  laneName: {
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.muted,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  laneCount: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  pips: { display: 'flex', flexWrap: 'wrap', gap: 2 },
  pip: {
    width: 12,
    height: 12,
    backgroundColor: colors.ok,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: 'transparent',
    transitionProperty: 'background-color, border-color',
    transitionDuration: '160ms',
  },
  pipSoon: { backgroundColor: colors.warn },
  pipOff: { backgroundColor: 'transparent', borderColor: colors.line2 },
  pipGone: { backgroundColor: 'transparent', borderStyle: 'dashed', borderColor: colors.line2 },
  legend: {
    display: 'flex',
    gap: space.lg,
    flexWrap: 'wrap',
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    paddingBlockStart: space.xs,
  },
  legendItem: { display: 'inline-flex', alignItems: 'center', gap: space.xs },
  mini: { width: 9, height: 9 },
  mark: {
    width: 30,
    height: 30,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    transitionProperty: 'background-color, color',
    transitionDuration: '160ms',
  },
  show: { backgroundColor: colors.okSoft, color: colors.ok, borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)` },
  present: {
    backgroundColor: colors.warnSoft,
    color: colors.warn,
    borderColor: `color-mix(in srgb, ${colors.warn} 35%, transparent)`,
  },
  hide: { backgroundColor: colors.idleSoft, color: colors.faint },
  svg: { width: 16, height: 16 },
});

export function Display() {
  const query = useDisplay();
  return (
    <Screen title="Display" query={query}>
      {(d) => <DisplayView d={d} />}
    </Screen>
  );
}

const Mark = ({ mode }: { mode: DisplayMode }) => (
  <span {...stylex.props(styles.mark, styles[mode])}>
    <svg
      {...stylex.props(styles.svg)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={MARK[mode]} />
    </svg>
  </span>
);

const DETAIL: Record<DisplayMode, (presenting: boolean) => string> = {
  show: () => 'Always on screen',
  present: (p) => (p ? 'Hidden now, back when you stop presenting' : 'On screen; hidden while presenting'),
  hide: () => 'Never shown',
};

function DisplayView({ d }: { d: DisplaySettings }) {
  const act = useAct();
  return (
    <>
      <PageHead
        eyebrow="settings · /display"
        title="Display"
        sub="Choose what this page shows. Presenting hides everything marked “Hide while presenting” in one switch, menus and links included; those pages answer “not found”. This page stays at /display."
      />
      <section {...stylex.props(styles.hero, d.presenting && styles.heroOn)} aria-label="Presenting">
        <div {...stylex.props(styles.control)}>
          <div {...stylex.props(styles.switchRow)}>
            <Switch
              on={d.presenting}
              label="Presenting"
              onToggle={() => act('/api/display/presenting', { on: !d.presenting }, { quiet: true })}
            />
            <div>
              <h2 {...stylex.props(styles.title)}>Presenting</h2>
              <div {...stylex.props(styles.state, d.presenting && styles.stateOn)}>{d.presenting ? 'On' : 'Off'}</div>
            </div>
          </div>
          <p {...stylex.props(styles.explain)}>
            {d.presenting
              ? 'Only what you allow is visible, with nothing on screen saying so.'
              : 'Everything is visible to you. Turn it on before sharing your screen.'}
          </p>
          <div {...stylex.props(styles.keys)}>
            <kbd {...stylex.props(styles.kbd)}>Alt</kbd>+<kbd {...stylex.props(styles.kbd)}>Shift</kbd>+
            <kbd {...stylex.props(styles.kbd)}>P</kbd>
            <span>from any page, or triple-click the logo</span>
          </div>
        </div>
        <Preview d={d} />
      </section>
      {d.groups.map((g, n) => (
        <Section key={g.name} title={g.name} icon={GROUP_ICON[g.name] ?? 'eye'}>
          <Appear i={n}>
            <Card>
              <List>
                {g.items.map((i) => (
                  <Row
                    key={i.key}
                    lead={<Mark mode={i.mode} />}
                    title={i.label}
                    detail={DETAIL[i.mode](d.presenting)}
                    actions={
                      <Segments
                        label={i.label}
                        value={i.mode}
                        options={MODES}
                        onChange={(v) => act('/api/display/mode', { key: i.key, value: v }, { quiet: true })}
                      />
                    }
                  />
                ))}
              </List>
            </Card>
          </Appear>
        </Section>
      ))}
    </>
  );
}

function Preview({ d }: { d: DisplaySettings }) {
  const items = d.groups.flatMap((g) => g.items);
  const on = items.filter((i) => visible(i.mode, d.presenting)).length;
  return (
    <div {...stylex.props(styles.preview)}>
      <div {...stylex.props(styles.previewHead)}>
        <span {...stylex.props(styles.previewLabel)}>On screen now</span>
        <span {...stylex.props(styles.previewCount)}>
          {on} of {items.length} visible
        </span>
      </div>
      {d.groups.map((g) => {
        const lit = g.items.filter((i) => visible(i.mode, d.presenting)).length;
        return (
          <div key={g.name} {...stylex.props(styles.lane)}>
            <span {...stylex.props(styles.laneName)}>{g.name}</span>
            <span {...stylex.props(styles.pips)}>
              {g.items.map((i) => (
                <i
                  key={i.key}
                  title={`${i.label}: ${visible(i.mode, d.presenting) ? 'visible' : 'hidden'}`}
                  {...stylex.props(
                    styles.pip,
                    i.mode === 'present' && (d.presenting ? styles.pipOff : styles.pipSoon),
                    i.mode === 'hide' && styles.pipGone,
                  )}
                />
              ))}
            </span>
            <span {...stylex.props(styles.laneCount)}>
              {lit}/{g.items.length}
            </span>
          </div>
        );
      })}
      <div {...stylex.props(styles.legend)}>
        <span {...stylex.props(styles.legendItem)}>
          <i {...stylex.props(styles.pip, styles.mini)} /> always shown
        </span>
        <span {...stylex.props(styles.legendItem)}>
          <i {...stylex.props(styles.pip, d.presenting ? styles.pipOff : styles.pipSoon, styles.mini)} />{' '}
          {d.presenting ? 'hidden while presenting' : 'hides while presenting'}
        </span>
        <span {...stylex.props(styles.legendItem)}>
          <i {...stylex.props(styles.pip, styles.pipGone, styles.mini)} /> always hidden
        </span>
      </div>
    </div>
  );
}
