// The JSON the hub's API returns (hub/screens.py and routes.py). Times are epoch seconds. `profile` is an agent id.

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'idle' | '';

export interface Action {
  type: 'link' | 'post';
  label: string;
  icon?: string | null;
  primary?: boolean;
  href?: string;
  url?: string;
  body?: Record<string, unknown>;
  confirm?: string | null;
}

export interface Event {
  at: number;
  kind: string;
  title: string;
  detail?: string;
  to?: string | null;
  ok?: boolean;
  source?: string;
}

export interface Nav {
  attention: number;
  agents: { name: string; up: boolean; companions: { name: string; display: string; live: boolean; waiting: number }[] }[];
  /** Colours chosen in cluster.toml, by agent id; the rest are picked from the id. */
  colors?: Record<string, string>;
  allAgents: boolean;
  system: { key: string; path: string; label: string; count?: number; note?: string }[];
  display: boolean;
}

export interface Container {
  name: string;
  service: string;
  state: string;
  status: string;
  image: string;
  healthy: boolean;
}

export interface Stack {
  id: string;
  label: string;
  profile: string | null;
  role: string | null;
  containers: Container[];
}

export interface Pool {
  size: number;
  used: number;
  avail: number;
}

export interface NeedItem {
  tone: 'bad' | 'warn' | 'info';
  icon: string;
  title: string;
  detail: string;
  since?: number;
  actions: Action[];
}

export interface Overview {
  tiles?: {
    agents: { online: number; total: number; link: boolean };
    companions?: { live: number; total: number; waiting: number; link: string };
    disk?: Pool | null;
    diskLabel?: string; // 'Server disk' (admins, shared pool) or 'Your disk' (a person's own)
    memory?: { usedMB: number; poolMB: number };
  };
  needs?: NeedItem[];
  activity?: Event[];
  stacks?: { at?: number; rows: Stack[] };
}

export interface Account {
  key: string;
  label: string;
  signedIn: boolean;
  active: boolean;
  detail: string;
}

export interface AgentCard {
  name: string;
  online: boolean;
  onboarded?: boolean;
  accounts?: Account[];
  connectors?: { key: string; name: string; added: boolean; signedIn: boolean }[];
  links?: { chat: string; terminal: string; files: string; browser: string | null };
  companions?: { name: string; display: string; live: boolean }[];
  resources?: { usedMB: number; limitMB: number | null; running: string[]; waiting: string[]; paused: number };
}

/** A one-time T3 pairing link (POST /api/agents/<id>/pair), or why there can't be one. */
export type PairLink =
  { available: true; kind: 'browser' | 'app'; url: string; expires: string; id: string } | { available: false; reason: string };

/** A browser or T3 app signed in to an agent's chat. */
export interface Device {
  id: string;
  label: string;
  ip: string;
  userAgent: string;
  created: string;
  lastSeen: string;
  expires: string;
  connected: boolean;
}

export interface Onboarding {
  done: boolean;
  ready: boolean; // at least one AI account is signed in, so it can be finished
  steps: { id: 'claude' | 'codex' | 'connectors' | 'github'; done: boolean; optional: boolean }[];
}

export interface Agents {
  agents: AgentCard[];
  memory?: { usedMB: number; poolMB: number };
}

export interface AgentPage {
  agent: AgentCard;
  up: boolean;
  companions: { name: string; display: string; state: CompanionState; tasks: number; working: number; waiting: number }[];
  containers?: Stack[];
  disk?: Pool | null; // the owner's own disk (per-person storage)
  owner: string;
  mine: boolean; // the viewer owns it (else an admin is looking)
}

export interface Flow {
  key: string;
  name: string;
  hint: string;
  mode: string;
  signedIn: boolean;
  detail: string;
  active: boolean;
  url: string;
  code: string;
  done: boolean;
  screen: string;
  mcpReady?: boolean;
}

export interface ConnectorFlow {
  active: boolean;
  url: string;
  finished: boolean;
  ok: boolean;
  screen: string;
}

export interface Connector {
  key: string;
  name: string;
  what: string;
  added: boolean;
  custom: boolean;
  ready: boolean;
  flow?: ConnectorFlow;
}

export interface AccountsPage {
  agent: string;
  owner: string;
  notice: string;
  keys: { label: string; value: string }[];
  ai: Flow[];
  github: Flow;
  connectors: Connector[];
  devices: Device[];
  onboarding: Onboarding;
  env?: Record<string, { masked: string; length: number }>;
  browserUp: boolean;
  browserUrl: string | null;
}

export type CompanionState = 'live' | 'disconnected' | 'offline' | 'unconfigured';
export type TaskStatus = 'working' | 'waiting' | 'done' | 'failed' | 'stopped';

export interface Task {
  id: string;
  title: string;
  kind: 'task' | 'errand' | 'review';
  requester: string;
  status: TaskStatus;
  waiting: string;
  outcome: string;
  startedAt: number;
  endedAt: number | null;
  slack: string;
  t3: string;
  poll: string | null; // the poll this task posted, if any
}

export interface Poll {
  id: string;
  task: string;
  open: boolean;
  closes: number;
  closed: number | null;
  question: string;
  channel: string;
  link: string;
  multiple: boolean;
  options: { label: string; votes: number; voters: { name: string; avatar: string }[] }[];
}

export interface SettingField {
  key: string;
  label: string;
  help?: string;
  type: 'choice' | 'bool' | 'text';
  options?: { value: string; label: string; help?: string }[];
  default?: unknown;
  value: unknown;
}

export interface Companion {
  name: string;
  display: string; // how it calls itself (cluster.json display_name)
  problem: string; // the last error its runner reported
  profile: string;
  state: CompanionState;
  since?: number;
  seen?: number;
  mode: string;
  tasks: Task[];
  events: Event[];
  sentThisWeek: Event[];
  delivered?: Event[];
  settings?: SettingField[];
  channels?: Channel[]; // present when the companion takes asks
  polls?: Poll[];
  pulls?: Pulls; // present when the companion has a GitHub App slot
}

export interface Pulls {
  github: { ready: boolean; bot: string; accounts: string[]; at: number; error: string };
  me: string; // the owner's GitHub username: their PRs are listed first
  items: Pull[];
}

export type Ci = 'passing' | 'failing' | 'running' | '';

export interface Pull {
  id: string; // owner/repo#123
  repo: string;
  number: number;
  title: string;
  url: string;
  draft: boolean;
  author: string;
  avatar: string;
  labels: { name: string; color: string }[];
  additions: number;
  deletions: number;
  created: string;
  updated: string;
  head: string;
  ci: Ci;
  review: PullReview | null; // the latest one
}

export interface PullReview {
  status: TaskStatus | 'queued';
  outcome: string;
  task: string;
  head: string; // the commit it reviewed
  at: string;
  url?: string;
  t3?: string;
  slack?: string;
  // what the latest finished review found; open = earlier findings that still stand
  counts?: { findings: number; blocking: number; open: number; qa: string } | null;
}

/** A companion's own secrets: what each is and whether it is set; values only on request. */
export interface CompanionSecrets {
  items: { file: string; name: string; label: string; about: string; how: string; set: boolean; modified: number | null }[];
}

export interface Channel {
  id: string;
  name: string;
  member: boolean; // the companion is in it, so it can post there
}

export interface Services {
  domains: { profile: string; stacks: Stack[] }[];
  other: Stack[];
}

export interface ConfigRow {
  id: string;
  label: string;
  profile: string | null;
  role: string | null;
  modified: number;
  companion: string | null;
}

export interface Configs {
  domains: { profile: string; stacks: ConfigRow[] }[];
  other: ConfigRow[];
}

export interface ConfigFile {
  id: string;
  label: string;
  role: string | null;
  text: string;
  path: string;
  deploys: Event[];
}

export interface FolderSize {
  path: string;
  bytes: number;
}

export interface ProfileUsage {
  name: string;
  total: number;
  top: FolderSize[];
  biggest: FolderSize[];
}

export interface DiskScan {
  at: number;
  took: number;
  profiles: ProfileUsage[];
}

/** A person's own disk (per-person storage) and their agents on it; no numbers while it is not mounted. */
export type PersonDisk = { email: string; agents: string[] } & Partial<Pool>;

export interface Storage {
  reported: boolean;
  mode: 'shared' | 'per-person';
  manage: boolean; // may rescan and clean up (admins)
  pool?: Pool | null;
  people: PersonDisk[];
  events: Event[];
  scan?: DiskScan;
}

export interface Secret {
  name: string;
  label: string;
  used_by: string[];
  about: string;
  how: string;
  modified: number;
  versions: number;
  effect: string;
  kinds: SecretKind[];
  /** '' for the cluster's own secrets; the label of [hub] extra_secrets for that folder's. */
  group: string;
}

/** What changing a secret does (the Secrets screen's filter). */
export type SecretKind = 'restart' | 'copy' | 'read' | 'unmapped';

export interface Secrets {
  items: Secret[];
  events: Event[];
}

export interface Notifications {
  configured: boolean; // a Bark server is set (BARK_URL); pushes are off without one
  barkUp: boolean;
  barkPublic: string;
  agents: number;
  watching: number;
  settings: { deviceKey: string; minMinutes: number; muted: boolean; encrypt: boolean; encKey: string };
  recent: Event[];
}

export type DisplayMode = 'show' | 'present' | 'hide';

export interface DisplaySettings {
  presenting: boolean;
  groups: { name: string; items: { key: string; label: string; mode: DisplayMode }[] }[];
}
