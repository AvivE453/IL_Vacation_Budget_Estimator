import OriginsList from "../components/OriginsList";

// The search form arrives in 3.2.2; for now the page shows the departure
// airports the form's dropdown will offer.
export default function SearchPage() {
  return (
    <>
      <h2>Search</h2>
      <h3>Departure airports</h3>
      <OriginsList />
    </>
  );
}
