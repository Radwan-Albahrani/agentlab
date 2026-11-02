import { useCallback, useEffect, type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTogglePresenting } from '../api/queries';

/** Presenting on/off without any trace on screen: Alt+Shift+P, or a triple click on the logo (returned handler). */
export function usePresentingSwitch() {
  const togglePresenting = useTogglePresenting();
  const navigate = useNavigate();
  const toggle = useCallback(async () => {
    const displayVisible = await togglePresenting();
    if (!displayVisible) navigate('/');
  }, [togglePresenting, navigate]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && e.shiftKey && e.code === 'KeyP') {
        e.preventDefault();
        void toggle();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [toggle]);

  return (e: MouseEvent) => {
    e.preventDefault();
    if (e.detail === 3) void toggle();
  };
}
