import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

declare global {
  var __UI_SDK_STRICT__: boolean | undefined;
}
globalThis.__UI_SDK_STRICT__ = true;

// jsdom has no top layer, animations or layout; UI SDK popups need these to open
const nothing = () => undefined;
HTMLElement.prototype.showPopover = nothing;
HTMLElement.prototype.hidePopover = nothing;
Element.prototype.getAnimations = () => [];
Element.prototype.scrollIntoView = nothing;
Element.prototype.checkVisibility = () => true;
Element.prototype.getClientRects = () => [] as unknown as DOMRectList;
document.elementFromPoint = () => null;
document.elementsFromPoint = () => [];
globalThis.ResizeObserver = class {
  observe = nothing;
  unobserve = nothing;
  disconnect = nothing;
};
document.head.append(Object.assign(document.createElement('style'), { textContent: '[popover] { display: block !important }' }));

afterEach(cleanup);
