import type { Event } from '../../api/types';
import { usePages } from '../../lib/usePages';
import { Card } from '../../ui/Card';
import { Appear } from '../../ui/motion';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { List, Row } from '../../ui/Row';
import { When } from '../../ui/When';
import { Mono } from './parts';

const PAGE = 6;

export function Delivered({ events }: { events: Event[] }) {
  const pages = usePages(events, PAGE);
  return (
    <Section title="Delivered" icon="send" sub="Who received what." right={<Pager {...pages} />}>
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
          <Empty title="Nothing sent yet" text="Messages, files and logins sent for you show up here." icon="send" />
        )}
      </Card>
    </Section>
  );
}
