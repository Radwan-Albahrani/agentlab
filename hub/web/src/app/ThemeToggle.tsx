import { useScheme } from '../theme/mode';
import { Button } from '../ui/Button';

/** Sun in dark, moon in light: one click switches to the other look. */
export function ThemeToggle() {
  const [scheme, toggle] = useScheme();
  const next = scheme === 'dark' ? 'light' : 'dark';
  return (
    <Button
      icon={scheme === 'dark' ? 'sun' : 'moon'}
      label={`Switch to ${next} theme`}
      variant="quiet"
      iconOnly
      small
      onClick={toggle}
    />
  );
}
