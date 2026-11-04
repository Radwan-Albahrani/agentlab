import type { Event } from '../../api/types';
import { usePages } from '../../lib/usePages';
import { Card } from '../../ui/Card';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { List, Row } from '../../ui/Row';
import { When } from '../../ui/When';

const PAGE = 6;

export function Delivered({ events }: { events: Event[] }) {
  const pages = usePages(events, PAGE);
  return (
    <Section title="Delivered" sub="Who received what." right={<Pager {...pages} />}>
      <Card>
        {events.length ? (
          <List>
            {pages.shown.map((e, i) => (
              <Row
                key={`${e.at}-${i}`}
                icon={e.kind === 'sent' ? 'send' : 'files'}
                tone={e.ok === false ? 'bad' : 'ok'}
                title={e.title}
                detail={e.detail}
                meta={<When t={e.at} />}
              />
            ))}
          </List>
        ) : (
          <Empty title="Nothing sent yet" text="Messages, files and logins sent for you show up here." icon="send" />
        )}
      </Card>
    </Section>
  );
}
