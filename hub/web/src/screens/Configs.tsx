import * as stylex from '@stylexjs/stylex';
import { Fragment, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { useConfigFile, useConfigs } from '../api/queries';
import type { ConfigFile, ConfigRow, Configs as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { domainSub, StackLead, StackName } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { ago, plural } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { CopyButton } from '../ui/actions';
import { Button, LinkButton } from '../ui/Button';
import { useAct, useFeedback } from '../ui/feedback';
import { FeedSection } from '../ui/Feed';
import { Icon } from '../ui/Icon';
import { StatGrid } from '../ui/layout';
import { Appear } from '../ui/motion';
import { PageHead, Section, Stat } from '../ui/page';
import { IconBox } from '../ui/Row';
import { Badge } from '../ui/status';
import { Mono } from '../ui/text';
import { When } from '../ui/When';

const styles = stylex.create({
  // the file list: one panel, a heading strip per agent, a row per compose file
  files: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  firstGroup: { borderTopWidth: 0 },
  groupIcon: { display: 'flex', color: colors.faint },
  groupName: {
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
  },
  groupSub: { fontSize: text.sm, color: colors.faint },
  file: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingInlineEnd: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
  },
  fileLink: {
    flex: '1',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.md,
    paddingInlineStart: space.xxl,
    color: { default: colors.fg, ':hover': colors.fg },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: -2,
  },
  fileText: { flex: '1', minWidth: 0 },
  path: {
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.faint,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  when: {
    fontFamily: font.mono,
    fontSize: text.xs,
    fontVariantNumeric: 'tabular-nums',
    color: colors.faint,
    whiteSpace: 'nowrap',
    display: { default: null, [media.phone]: 'none' },
  },
  chevron: { display: 'flex', color: colors.faint },
  // settings shortcuts as cells of one hairline strip
  links: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    overflow: 'hidden',
  },
  linkTile: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    backgroundColor: { default: colors.panel, ':hover': colors.hover },
    color: { default: colors.fg, ':hover': colors.fg },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: -2,
  },
  linkText: { flex: '1', minWidth: 0 },
  linkSub: { fontSize: text.md, color: colors.muted },
  // the viewer
  crumb: { color: { default: colors.faint, ':hover': colors.fg } },
  editor: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  tab: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.xxs,
    paddingInline: space.md,
    borderRadius: radius.sm,
    fontFamily: font.mono,
    fontSize: text.sm,
    fontWeight: 600,
    color: colors.fg,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  tabIcon: { display: 'flex', color: colors.muted },
  meta: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    letterSpacing: '.06em',
    textTransform: 'uppercase',
    color: colors.faint,
    whiteSpace: 'nowrap',
  },
  spacer: { flex: '1' },
  code: {
    display: 'grid',
    gridTemplateColumns: 'auto minmax(max-content, 1fr)', // long lines scroll sideways inside, never the page
    maxHeight: '68vh',
    overflow: 'auto',
    backgroundColor: colors.sunk,
    fontFamily: font.mono,
    fontSize: text.sm,
    lineHeight: 1.75,
  },
  gutter: {
    position: 'sticky',
    left: 0,
    zIndex: 1,
    paddingBlock: space.lg,
    paddingInline: space.lg,
    textAlign: 'right',
    color: colors.faint,
    userSelect: 'none',
    whiteSpace: 'pre',
    fontVariantNumeric: 'tabular-nums',
    backgroundColor: colors.sunk,
    borderRightWidth: 1,
    borderRightStyle: 'solid',
    borderRightColor: colors.line,
  },
  lines: { margin: 0, paddingBlock: space.lg, paddingInline: space.xxl, whiteSpace: 'pre', color: colors.fg, tabSize: 2 },
  key: { color: colors.info },
  dash: { color: colors.faint },
  comment: { color: colors.faint, fontStyle: 'italic' },
  foot: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    flexWrap: 'wrap',
    paddingBlock: space.md,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  footIcon: { display: 'flex', flexShrink: 0, color: colors.faint },
  footText: { flex: '1', minWidth: 240, fontSize: text.md, color: colors.muted },
});

export function Configs() {
  const query = useConfigs();
  return (
    <Screen title="Configs" query={query}>
      {(d) => <ConfigsView d={d} />}
    </Screen>
  );
}

const composePath = (id: string) => `rendered/compose/${id}/docker-compose.yml`;

function ConfigsView({ d }: { d: Data }) {
  const canSee = useCanSee();
  const all = [...d.domains.flatMap((x) => x.stacks), ...d.other];
  const latest = all.reduce<ConfigRow | null>((a, s) => (!a || s.modified > a.modified ? s : a), null);
  const companions = all.filter((s) => s.role && s.role !== 'agent').length;
  let row = 0; // one stagger down the whole list
  return (
    <>
      <PageHead
        eyebrow={`rendered from cluster.toml · ${plural(all.length, 'compose file')}`}
        title="Configs"
        sub="The compose file of every stack, each agent with its companions. agentctl renders them from cluster.toml; deploying one only recreates the services whose definition changed."
      />
      <StatGrid>
        <Stat
          label="Compose files"
          value={all.length}
          sub={d.other.length ? `${plural(d.other.length, 'infrastructure stack')} among them` : undefined}
        />
        <Stat label="Agents" value={d.domains.length} sub={plural(companions, 'companion')} />
        <Stat label="Last rendered" value={latest ? ago(latest.modified) : '—'} sub={latest?.label} />
      </StatGrid>
      <Section title="Stacks" icon="files" sub="Open one to read it and deploy it.">
        <div {...stylex.props(styles.files)}>
          {d.domains.map((x, n) => (
            <div key={x.profile} {...stylex.props(hueTheme(x.profile))}>
              <div {...stylex.props(styles.group, n === 0 && styles.firstGroup)}>
                <Badge name={x.profile} size="xs" />
                <span {...stylex.props(styles.groupName)}>{x.profile}</span>
                <span {...stylex.props(styles.groupSub)}>{domainSub(x.stacks.length)}</span>
              </div>
              {x.stacks.map((s) => (
                <FileRow key={s.id} s={s} i={row++} />
              ))}
            </div>
          ))}
          {d.other.length > 0 && (
            <div>
              <div {...stylex.props(styles.group, !d.domains.length && styles.firstGroup)}>
                <span {...stylex.props(styles.groupIcon)}>
                  <Icon name="layers" size={14} />
                </span>
                <span {...stylex.props(styles.groupName)}>Infrastructure</span>
                <span {...stylex.props(styles.groupSub)}>{plural(d.other.length, 'stack')}</span>
              </div>
              {d.other.map((s) => (
                <FileRow key={s.id} s={s} i={row++} />
              ))}
            </div>
          )}
        </div>
      </Section>
      {(canSee('/secrets') || canSee('/notifications')) && (
        <Section title="Other settings" icon="key">
          <div {...stylex.props(styles.links)}>
            {canSee('/secrets') && (
              <LinkTile to="/secrets" icon="key" title="Secrets" sub="Tokens and passwords, applied where they are used" />
            )}
            {canSee('/notifications') && (
              <LinkTile to="/notifications" icon="bell" title="Notifications" sub="Phone pushes through Bark (optional)" />
            )}
          </div>
        </Section>
      )}
    </>
  );
}

function FileRow({ s, i }: { s: ConfigRow; i: number }) {
  return (
    <Appear i={i}>
      <div {...stylex.props(styles.file)}>
        <Link to={`/config/${s.id}`} {...stylex.props(styles.fileLink)} aria-label={`View ${s.label}`}>
          {s.profile ? <StackLead stack={s} /> : <IconBox icon="layers" />}
          <div {...stylex.props(styles.fileText)}>
            <div>{s.profile ? <StackName stack={s} /> : <b>{s.label}</b>}</div>
            <div {...stylex.props(styles.path)}>{composePath(s.id)}</div>
          </div>
          <span {...stylex.props(styles.when)}>
            <When t={s.modified} />
          </span>
          <span {...stylex.props(styles.chevron)}>
            <Icon name="arrow" size={17} />
          </span>
        </Link>
        {s.companion && (
          <LinkButton
            label="Settings"
            icon="bot"
            variant="quiet"
            small
            iconOnly
            to={`/agents/${s.profile}/${s.companion}#settings`}
          />
        )}
      </div>
    </Appear>
  );
}

function LinkTile({ to, icon, title, sub }: { to: string; icon: string; title: string; sub: string }) {
  return (
    <Link to={to} {...stylex.props(styles.linkTile)}>
      <IconBox icon={icon} />
      <div {...stylex.props(styles.linkText)}>
        <b>{title}</b>
        <div {...stylex.props(styles.linkSub)}>{sub}</div>
      </div>
      <span {...stylex.props(styles.chevron)}>
        <Icon name="arrow" size={17} />
      </span>
    </Link>
  );
}

export function ConfigEdit() {
  const id = useLocation().pathname.replace(/^\/config\//, '');
  const query = useConfigFile(id);
  return (
    <Screen title="Config" query={query}>
      {(d) => <Viewer d={d} />}
    </Screen>
  );
}

/** One line of YAML with its key, list dash and comment told apart. */
function YamlLine({ line }: { line: string }): ReactNode {
  const comment = /^(\s*)(#.*)$/.exec(line);
  if (comment)
    return (
      <>
        {comment[1]}
        <span {...stylex.props(styles.comment)}>{comment[2]}</span>
      </>
    );
  const m = /^(\s*)(- )?([\w.-]+)(:)(\s.*|)$/.exec(line);
  if (!m) {
    const dash = /^(\s*)(- )(.*)$/.exec(line);
    if (!dash) return line;
    return (
      <>
        {dash[1]}
        <span {...stylex.props(styles.dash)}>{dash[2]}</span>
        {dash[3]}
      </>
    );
  }
  return (
    <>
      {m[1]}
      {m[2] && <span {...stylex.props(styles.dash)}>{m[2]}</span>}
      <span {...stylex.props(styles.key)}>{m[3]}</span>
      {m[4]}
      {m[5]}
    </>
  );
}

/** Read-only: agentctl renders it from cluster.toml. */
function Viewer({ d }: { d: ConfigFile }) {
  const act = useAct();
  const { confirm } = useFeedback();
  const warn =
    d.role === 'agent'
      ? 'Deploying recreates this agent: running chats are interrupted (they can be continued).'
      : 'Only services whose definition changed are recreated.';

  const deploy = async () => {
    if (await confirm(`Deploy ${d.id}? ${warn}`)) await act('/api/config/deploy', { id: d.id });
  };

  const lines = d.text.replace(/\n$/, '').split('\n');
  const file = d.path.split('/').pop() ?? d.path;
  return (
    <>
      <PageHead
        eyebrow={
          <Link to="/config" {...stylex.props(styles.crumb)}>
            Configs ›
          </Link>
        }
        title={d.label}
        sub={<Mono>{d.path}</Mono>}
        right={<LinkButton label="Services" icon="layers" to="/services" />}
      />
      <section {...stylex.props(styles.editor)} aria-label={file}>
        <div {...stylex.props(styles.bar)}>
          <span {...stylex.props(styles.tab)}>
            <span {...stylex.props(styles.tabIcon)}>
              <Icon name="files" size={15} />
            </span>
            {file}
          </span>
          <span {...stylex.props(styles.meta)}>{plural(lines.length, 'line')} · YAML · read only</span>
          <span {...stylex.props(styles.spacer)} />
          <CopyButton text={d.text} />
          <Button label="Deploy" icon="send" variant="primary" small onClick={deploy} />
        </div>
        <div {...stylex.props(styles.code)}>
          <div {...stylex.props(styles.gutter)} aria-hidden="true">
            {lines.map((_, i) => i + 1).join('\n')}
          </div>
          <pre {...stylex.props(styles.lines)}>
            {lines.map((l, i) => (
              <Fragment key={i}>
                <YamlLine line={l} />
                {'\n'}
              </Fragment>
            ))}
          </pre>
        </div>
        <div {...stylex.props(styles.foot)}>
          <span {...stylex.props(styles.footIcon)}>
            <Icon name="sliders" size={15} />
          </span>
          <span {...stylex.props(styles.footText)}>
            Rendered by agentctl. To change it, edit <Mono>/etc/agentlab/cluster.toml</Mono> and run <Mono>agentctl apply</Mono>.{' '}
            {warn}
          </span>
        </div>
      </section>
      <FeedSection title="Deploys" events={d.deploys} />
    </>
  );
}
