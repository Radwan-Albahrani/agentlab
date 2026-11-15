import * as stylex from '@stylexjs/stylex';
import { useState, type ReactNode } from 'react';
import type { Connector } from '../../api/types';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { InlineForm, SubmitField, TextInput } from '../../ui/inputs';
import { Pill } from '../../ui/status';
import { BrandMark, FlowBox, FlowEnd, LiveEdge, OpenSignInStep, Result, Step, Steps, Terminal } from './flow';
import { useAccountAct } from './useAccountAct';

const styles = stylex.create({
  // cells share hairlines: the grid draws the top and left edge, each tile its right and bottom
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))',
    alignItems: 'stretch',
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    borderLeftWidth: 1,
    borderLeftStyle: 'solid',
    borderLeftColor: colors.line,
  },
  cell: {
    borderRightWidth: 1,
    borderRightStyle: 'solid',
    borderRightColor: colors.line,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    minWidth: 0,
  },
  tile: {
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    gap: space.md,
    padding: space.xl,
    backgroundColor: colors.panel,
  },
  // not added yet: sits back on the page colour
  idle: { backgroundColor: colors.bg },
  idleName: { color: colors.muted },
  // signing in: the tile opens across the row to make room for the steps
  active: {
    gridColumnStart: 1,
    gridColumnEnd: -1,
    gap: space.lg,
    padding: { default: space.xxl, [media.phone]: space.lg },
    backgroundColor: colors.raised,
  },
  head: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: space.sm, minWidth: 0 },
  who: { display: 'grid', gap: space.xxxs, minWidth: 0 },
  name: { fontFamily: font.display, fontWeight: 600, fontSize: text.body, overflowWrap: 'anywhere' },
  what: { color: colors.muted, fontSize: text.sm, overflowWrap: 'anywhere' },
  foot: { display: 'flex', alignItems: 'center', gap: space.xs, flexWrap: 'wrap', marginTop: 'auto' },
  spacer: { flex: '1' },
  add: {
    gridColumnStart: 1,
    gridColumnEnd: -1,
    display: 'flex',
    alignItems: 'center',
    gap: space.xl,
    flexWrap: 'wrap',
    padding: space.xl,
    backgroundColor: { default: colors.bg, ':focus-within': colors.panel },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
  },
  addIcon: {
    width: 36,
    height: 36,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    color: colors.muted,
  },
  addText: { flexGrow: 1, flexShrink: 1, flexBasis: '200px', minWidth: 0 },
  addForm: { flexGrow: 999, flexShrink: 1, flexBasis: '360px', minWidth: 0 },
});

/** Connector tiles on shared hairlines; one signing in spans the row. */
export const ConnectorGrid = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.grid)}>{children}</div>;

export function ConnectorTile({ agent, c }: { agent: string; c: Connector }) {
  const run = useAccountAct(agent);
  const f = c.flow;
  const remove = () => run({ action: 'mcp-remove', p: c.key }, `${c.ready ? 'Sign out of' : 'Remove'} ${c.name} on ${agent}?`);
  let state: ReactNode = null;
  let actions: ReactNode;
  if (!c.added) {
    actions = <Button label="Connect" icon="plus" small onClick={() => run({ action: 'mcp-add', p: c.key })} />;
  } else if (c.ready) {
    state = <Pill tone="ok">Ready</Pill>;
    actions = (
      <>
        <span {...stylex.props(styles.spacer)} />
        <Button label="Sign out" variant="quiet" small onClick={remove} />
      </>
    );
  } else {
    state = <Pill tone={f?.active ? 'info' : 'warn'}>{f?.active ? 'Signing in…' : 'Not signed in'}</Pill>;
    actions = (
      <>
        {!f?.active && <Button label="Sign in" variant="primary" small onClick={() => run({ action: 'mcp-login', p: c.key })} />}
        <span {...stylex.props(styles.spacer)} />
        <Button label="Remove" variant="quiet" small onClick={remove} />
      </>
    );
  }
  return (
    <div {...stylex.props(styles.cell, styles.tile, !c.added && styles.idle, f?.active && styles.active)}>
      {f?.active && <LiveEdge />}
      <div {...stylex.props(styles.head)}>
        <BrandMark name={c.key} label={c.name} />
        {state}
      </div>
      <div {...stylex.props(styles.who)}>
        <div {...stylex.props(styles.name, !c.added && styles.idleName)}>{c.name}</div>
        <div {...stylex.props(styles.what)}>{c.what}</div>
      </div>
      {f?.active && (
        <FlowBox>
          <Steps>
            <OpenSignInStep provider={c.name} url={f.url} title="Open the sign-in page and approve" />
            <Step
              n={2}
              last
              done={f.finished}
              now={!!f.url && !f.finished}
              title="Paste the address that fails to load"
              sub={
                <>
                  After approving you land on a <b>localhost</b> or <b>127.0.0.1</b> page that won&apos;t open. Copy that whole
                  address here.
                </>
              }
            >
              <SubmitField
                placeholder="localhost:…/oauth/callback?code=…"
                button="Finish"
                onSubmit={(text) => run({ action: 'mcp-send', p: c.key, text })}
              />
            </Step>
          </Steps>
          <Terminal screen={f.screen} />
          <FlowEnd
            finished={f.finished}
            ok={
              f.ok ? (
                <Result ok>Signed in, for Claude and Codex.</Result>
              ) : (
                f.finished && <Result ok={false}>Sign-in ended without success; see Terminal and try again.</Result>
              )
            }
            onEnd={() => run({ action: 'mcp-stop', p: c.key })}
          />
        </FlowBox>
      )}
      <div {...stylex.props(styles.foot)}>{actions}</div>
    </div>
  );
}

export function AddConnector({ agent }: { agent: string }) {
  const run = useAccountAct(agent);
  const [server, setServer] = useState({ name: '', url: '' });
  const add = async () => {
    if (await run({ action: 'mcp-custom', ...server })) setServer({ name: '', url: '' });
  };
  return (
    <div {...stylex.props(styles.cell, styles.add)}>
      <span {...stylex.props(styles.addIcon)}>
        <Icon name="plus" size={18} />
      </span>
      <div {...stylex.props(styles.addText)}>
        <div {...stylex.props(styles.name)}>Any MCP server</div>
        <div {...stylex.props(styles.what)}>A remote MCP address from the service&apos;s docs, with a short name.</div>
      </div>
      <div {...stylex.props(styles.addForm)}>
        <InlineForm onSubmit={add}>
          <TextInput
            width="short"
            value={server.name}
            onChange={(v) => {
              setServer({ ...server, name: v });
            }}
            placeholder="name, e.g. stripe"
          />
          <TextInput
            value={server.url}
            onChange={(v) => {
              setServer({ ...server, url: v });
            }}
            placeholder="https://mcp.example.com/mcp"
          />
          <Button type="submit" label="Add" />
        </InlineForm>
      </div>
    </div>
  );
}
