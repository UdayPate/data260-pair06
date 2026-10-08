// The numbers shown on the Home page. page_size=1 because we only need the "total".
import api from "./api";

const total = (path) => api.get(path, { params: { page_size: 1 } }).then((r) => r.data.total);

export async function loadStudentStats() {
  const [applications, events] = await Promise.all([total("/applications/mine"), total("/events/registered")]);
  return { applications, events };
}

export async function loadCompanyStats() {
  const [jobs, events] = await Promise.all([total("/jobs/mine"), total("/events/mine")]);
  return { jobs, events };
}
