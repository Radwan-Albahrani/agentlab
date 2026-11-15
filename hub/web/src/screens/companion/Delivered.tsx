import { useState } from 'react';
import type { Event } from '../../api/types';
import { SENT_FILTERS, sentTo, type SentTo } from '../../lib/companion';
import { usePages } from '../../lib/usePages';
import { Card } from '../../ui/Card';
import { Segments } from '../../ui/controls';
import { Inline } from '../../ui/layout';
import { Appear } from '../../ui/motion';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { List, Row } from '../../ui/Row';
import { When } from '../../ui/When';
import { Mono } from './parts';

const PAGE = 6;

export function Delivered({ events: all }: { events: Event[] }) {
  const [to, setTo] = useState<SentTo>('all');
  const events = to === 'all' ? all : all.filter((e) => sentTo(e) === to);
  const pages = usePages(events, PAGE);
  const options = SENT_FILTERS.map((f) => ({
    ...f,
    count: f.value === 'all' ? all.length : all.filter((e) => sentTo(e) === f.value).length,
  }));
  return (
    <Section
      title="Sent"
      icon="send"
      sub="Everything it delivered: DMs to people, channel posts, files and GitHub reviews."
      right={
        <Inline gap="md">
          <Segments
            label="Filter deliveries"
            value={to}
            options={options}
            onChange={(v) => {
              setTo(v);
              pages.setPage(0);
            }}
          />
          <Pager {...pages} />
        </Inline>
      }
    >
      <Card>
        {events.length ? (
          <List>
            {pages.shown.map((e, i) => (
              <Appear key={`${e.at}-${i}`} i={i}>
                <Row
                  icon={e.ok === false ? 'alert' : e.kind === 'sent' ? 'send' : 'files'}
                  tone={e.ok === false ? 'bad' : 'idle'}
                  accent={e.ok === false ? 'bad' : undefined}
                  title={
                    <>
                      {e.title}
                      {e.to && <> → {e.to}</>}
                    </>
                  }
                  detail={e.detail}
                  meta={
                    <Mono>
                      <When t={e.at} />
                    </Mono>
                  }
                />
              </Appear>
            ))}
          </List>
        ) : (
          <Empty
            title={all.length ? 'Nothing here' : 'Nothing sent yet'}
            text={all.length ? 'Nothing it sent matches this filter.' : 'Messages, files and logins sent for you show up here.'}
            icon="send"
          />
        )}
      </Card>
    </Section>
  );
}
