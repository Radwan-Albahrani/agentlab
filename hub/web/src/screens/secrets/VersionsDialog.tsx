import { useSecretVersions } from '../../api/queries';
import { versionLabel } from '../../lib/format';
import { ActButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Dialog, DialogActions } from '../../ui/Dialog';
import { List, Row } from '../../ui/Row';
import { Mono } from '../../ui/text';

export function VersionsDialog({ name, onClose }: { name: string | null; onClose: () => void }) {
  const { data } = useSecretVersions(name);
  return (
    <Dialog
      open={name !== null}
      onClose={onClose}
      title={`Versions of ${name ?? ''}`}
      text="Restoring keeps the current value as a version too."
    >
      <List>
        {name &&
          data?.versions.map((v) => (
            <Row
              key={v}
              title={<Mono>{versionLabel(v)}</Mono>}
              actions={
                <ActButton
                  label="Restore"
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
