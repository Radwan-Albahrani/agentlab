import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState } from 'react';
import { useCompanionLogs, useCompanionSecrets } from '../../api/queries';
import type { CompanionSecrets as Data } from '../../api/types';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { useAct } from '../../ui/feedback';
import { SubmitField } from '../../ui/inputs';
import { Empty, Section } from '../../ui/page';
import { IconBox, List, Row } from '../../ui/Row';
import { Appear } from '../../ui/motion';
import { Pill } from '../../ui/status';
import { Note } from '../../ui/text';
import { When } from '../../ui/When';
import { LiveLine, Mono } from './parts';

const styles = stylex.create({
  open: { backgroundColor: colors.raised },
  console: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.sunk,
  },
  bar: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    fontSize: text.xxs,
    color: colors.muted,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    backgroundColor: colors.panel,
  },
  file: { fontWeight: 600, color: colors.fg },
  dot: { width: 7, height: 7, flexShrink: 0, backgroundColor: colors.info },
  count: { marginInlineStart: 'auto', fontVariantNumeric: 'tabular-nums', color: colors.faint },
  pre: {
    margin: 0,
    maxHeight: '62vh',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    lineHeight: 1.65,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    color: colors.fg,
  },
  line: { display: 'block' },
  stamp: { color: colors.faint, marginInlineEnd: space.md },
  bad: { color: colors.bad },
  warn: { color: colors.warn },
});

export function CompanionSecrets({ name, display }: { name: string; display: string }) {
  const query = useCompanionSecrets(name);
  const missing = query.data?.items.filter((s) => !s.set).length ?? 0;
  return (
    <Section
      title="Secrets"
      icon="key"
      sub={`What ${display} signs in with. Saving one restarts it with the new value; they are never shown again here.`}
      right={
        query.data && (
          <Pill tone={missing ? 'warn' : 'ok'} dot={!missing}>
            {missing ? `${missing} missing` : 'All set'}
          </Pill>
        )
      }
    >
      <Card>{query.data ? <SecretList name={name} d={query.data} /> : <Empty title="Loading…" icon="clock" />}</Card>
    </Section>
  );
}

function SecretList({ name, d }: { name: string; d: Data }) {
  const act = useAct();
  const [open, setOpen] = useState<string | null>(null);
  // the missing ones first: they are what stops the companion
  const items = [...d.items].sort((a, b) => Number(a.set) - Number(b.set));
  if (!items.length) return <Empty title="No secrets" text="This companion signs in with nothing of its own." icon="key" />;
  return (
    <List>
      {items.map((s, i) => (
        <Appear key={s.file} i={i}>
          <div {...stylex.props(open === s.file && styles.open)}>
            <Row
              accent={s.set ? undefined : 'warn'}
              lead={<IconBox icon={s.set ? 'key' : 'alert'} tone={s.set ? 'idle' : 'warn'} />}
              title={s.label || s.file}
              detail={s.about}
              meta={
                s.set ? (
                  <Mono>
                    <When t={s.modified} />
                  </Mono>
                ) : undefined
              }
              actions={
                <>
                  <Pill tone={s.set ? 'ok' : 'warn'}>{s.set ? 'Set' : 'Not set'}</Pill>
                  <Button
                    label={s.set ? 'Replace' : 'Set'}
                    variant={s.set ? 'quiet' : 'primary'}
                    small
                    onClick={() => {
                      setOpen(open === s.file ? null : s.file);
                    }}
                  />
                </>
              }
            />
            {open === s.file && (
              <CardBody divided>
                {s.how && <Note>{s.how}</Note>}
                <SubmitField
                  type="password"
                  placeholder={s.file}
                  button="Save"
                  onSubmit={async (value) => {
                    if (await act(`/api/companions/${name}/secret`, { file: s.file, value })) setOpen(null);
                  }}
                />
              </CardBody>
            )}
          </div>
        </Appear>
      ))}
    </List>
  );
}

const STAMP = /^(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?)\s+(.*)$/;
const toneOf = (line: string) =>
  /\b(error|exception|traceback|failed|critical)\b/i.test(line) ? styles.bad : /\bwarn(ing)?\b/i.test(line) ? styles.warn : null;

function LogLine({ line }: { line: string }) {
  const m = STAMP.exec(line);
  const rest = m ? (m[2] ?? '') : line;
  return (
    <span {...stylex.props(styles.line, toneOf(rest))}>
      {m && <span {...stylex.props(styles.stamp)}>{m[1]}</span>}
      {rest || ' '}
    </span>
  );
}

export function CompanionLogs({ name }: { name: string }) {
  const query = useCompanionLogs(name);
  const logs = query.data;
  const pre = useRef<HTMLPreElement>(null);
  const pinned = useRef(true); // follows new lines until you scroll up
  const lines = logs?.text ? logs.text.replace(/\n$/, '').split('\n') : [];
  useEffect(() => {
    const el = pre.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [logs?.text]);
  return (
    <Section
      title="Logs"
      icon="log"
      sub={
        logs?.at ? (
          <>
            Updated{' '}
            <Mono>
              <When t={logs.at} />
            </Mono>{' '}
            · refreshes by itself
          </>
        ) : (
          'Nothing logged yet.'
        )
      }
      right={logs?.text ? <CopyButton text={logs.text} /> : undefined}
    >
      {logs?.text ? (
        <div {...stylex.props(styles.console)}>
          <div {...stylex.props(styles.bar)}>
            <i {...stylex.props(styles.dot)} />
            <span {...stylex.props(styles.file)}>Live log</span>
            <span {...stylex.props(styles.count)}>{lines.length.toLocaleString()} lines</span>
            <LiveLine />
          </div>
          <pre
            ref={pre}
            {...stylex.props(styles.pre)}
            data-logs
            onScroll={(e) => {
              const el = e.currentTarget;
              pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            }}
          >
            {lines.map((l, i) => (
              <LogLine key={i} line={l} />
            ))}
          </pre>
        </div>
      ) : (
        <Card>
          <Empty title="No log yet" text="It appears once the companion has started." icon="log" />
        </Card>
      )}
    </Section>
  );
}
