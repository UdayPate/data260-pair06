import Card from "react-bootstrap/Card";
import Tab from "react-bootstrap/Tab";
import Tabs from "react-bootstrap/Tabs";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import PreferencesForm from "../components/PreferencesForm";
import ProfileForm from "../components/ProfileForm";
import { useAsync } from "../hooks/useAsync";
import { getMyPreferences, getMyProfile } from "../services/profileService";
import { getOptions } from "../services/metaService";

// Loads everything first, then shows the two forms. The forms start from the loaded data,
// so they are only created once it has arrived.
const loadAll = () => Promise.all([getMyProfile(), getMyPreferences(), getOptions()]);

export default function Profile() {
  const { data, loading, error, reload } = useAsync(loadAll, []);
  return (
    <>
      <PageHeader title="My profile" subtitle="Keep your details and preferences up to date." />
      {loading && <Loading label="Loading your profile…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && (
        <Card>
          <Card.Body>
            <Tabs defaultActiveKey="profile" className="mb-4">
              <Tab eventKey="profile" title="Profile">
                <ProfileForm profile={data[0]} options={data[2]} />
              </Tab>
              <Tab eventKey="preferences" title="Job & event preferences">
                <PreferencesForm prefs={data[1]} options={data[2]} />
              </Tab>
            </Tabs>
          </Card.Body>
        </Card>
      )}
    </>
  );
}
