import { useSecretVersions } from '../../api/queries';
import { versionLabel } from '../../lib/format';
import { ActButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Dialog, DialogActions } from '../../ui/Dialog';
import { Empty } from '../../ui/page';
import { List, Row } from '../../ui/Row';
import { Mono } from '../../ui/text';

export function VersionsDialog({ name, onClose }: { name: string | null; onClose: () => void }) {
  const { data } = useSecretVersions(name);
  const versions = name ? data?.versions : undefined;
  return (
    <Dialog
      open={name !== null}
      onClose={onClose}
      title={`Versions of ${name ?? ''}`}
      text="Newest first. Restoring keeps the current value as a version too."
    >
      {versions?.length === 0 && (
        <Empty title="No earlier versions" text="One is kept each time the value changes." icon="history" />
      )}
      <List>
        {versions?.map((v, i) => (
          <Row
            key={v}
            icon="history"
            tone={i === 0 ? 'info' : 'idle'}
            title={<Mono>{versionLabel(v)}</Mono>}
            detail={i === 0 ? 'the value before the current one' : undefined}
            actions={
              <ActButton
                label="Restore"
                icon="refresh"
                small
                url="/api/secrets/restore"
                body={{ name, version: v }}
                confirm={`Restore ${name} to this version?`}
              />
            }
          />
        ))}
      </List>
      <DialogActions>
        <Button label="Close" onClick={onClose} />
      </DialogActions>
    </Dialog>
  );
}
