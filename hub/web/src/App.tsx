import { Route, Routes } from 'react-router-dom';
import { Shell } from './app/Shell';
import { NotFound } from './app/Screen';
import { Accounts } from './screens/accounts';
import { Onboarding } from './screens/accounts/Onboarding';
import { Agent } from './screens/Agent';
import { Agents } from './screens/Agents';
import { Companion } from './screens/companion';
import { ConfigEdit, Configs } from './screens/Configs';
import { Display } from './screens/Display';
import { Notifications } from './screens/Notifications';
import { Overview } from './screens/Overview';
import { Secrets } from './screens/secrets';
import { Services } from './screens/Services';
import { Storage } from './screens/Storage';

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/agents/:name" element={<Agent />} />
        <Route path="/agents/:name/accounts" element={<Accounts />} />
        <Route path="/agents/:name/onboarding" element={<Onboarding />} />
        <Route path="/agents/:profile/:name" element={<Companion />} />
        <Route path="/services" element={<Services />} />
        <Route path="/config" element={<Configs />} />
        <Route path="/config/*" element={<ConfigEdit />} />
        <Route path="/storage" element={<Storage />} />
        <Route path="/secrets" element={<Secrets />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/display" element={<Display />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}
