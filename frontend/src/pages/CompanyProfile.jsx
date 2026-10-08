import Card from "react-bootstrap/Card";
import CompanyProfileForm from "../components/CompanyProfileForm";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import { useAsync } from "../hooks/useAsync";
import { getMyCompany } from "../services/companyService";

export default function CompanyProfile() {
  const { data, loading, error, reload } = useAsync(getMyCompany, []);
  return (
    <>
      <PageHeader title="Company profile" subtitle="This is what students see on your jobs and events." />
      {loading && <Loading label="Loading your profile…" />}
      <ErrorAlert message={error} onRetry={reload} />
      {data && <Card><Card.Body><CompanyProfileForm company={data} /></Card.Body></Card>}
    </>
  );
}
