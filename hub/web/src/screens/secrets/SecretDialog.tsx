import { useState } from 'react';
import { useSecretValue } from '../../api/queries';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Dialog, DialogActions } from '../../ui/Dialog';
import { useAct } from '../../ui/feedback';
import { Field, TextArea, TextInput } from '../../ui/inputs';
import { Spacer } from '../../ui/layout';
import { Note } from '../../ui/text';

export type Opened = { mode: 'view' | 'edit'; name: string } | { mode: 'new' };

const HINT = {
  view: 'Read only. Use Edit to change it.',
  edit: 'Saving applies it within 30 s wherever it is used. The current value is kept as a version.',
  new: 'Saved to the secrets folder (companions/<name>/<file> for a companion). Map it in hub/secrets-map.json to have it applied anywhere.',
};

/** View, edit or create a secret. The value is fetched when the dialog opens and never cached. */
export function SecretDialog({ opened, onClose }: { opened: Opened | null; onClose: () => void }) {
  const name = opened && opened.mode !== 'new' ? opened.name : null;
  const { data, error } = useSecretValue(name);
  const title = !opened ? '' : opened.mode === 'new' ? 'New secret' : opened.name;
  return (
    <Dialog open={opened !== null} onClose={onClose} title={title} text={opened && HINT[opened.mode]}>
      {opened?.mode === 'new' && <SecretForm key="new" mode="new" initialName="" initialValue="" onDone={onClose} />}
      {opened && opened.mode !== 'new' && data && (
        <SecretForm key={opened.name} mode={opened.mode} initialName={opened.name} initialValue={data.value} onDone={onClose} />
      )}
      {error && <Note>{error.message}</Note>}
    </Dialog>
  );
}

function SecretForm({
  mode,
  initialName,
  initialValue,
  onDone,
}: {
  mode: Opened['mode'];
  initialName: string;
  initialValue: string;
  onDone: () => void;
}) {
  const act = useAct();
  const [name, setName] = useState(initialName);
  const [value, setValue] = useState(initialValue);
  const save = async () => {
    if (await act(mode === 'new' ? '/api/secrets/create' : '/api/secrets/save', { name, value })) onDone();
  };
  return (
    <>
      {mode === 'new' && (
        <Field label="File name">
          <TextInput value={name} onChange={setName} placeholder="service-token.txt" />
        </Field>
      )}
      <Field label="Value">
        <TextArea value={value} readOnly={mode === 'view'} onChange={setValue} />
      </Field>
      <DialogActions>
        {mode !== 'new' && <CopyButton text={value} small={false} />}
        <Spacer />
        <Button label="Close" onClick={onDone} />
        {mode !== 'view' && <Button label="Save" variant="primary" onClick={save} />}
      </DialogActions>
    </>
  );
}
