import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api, type Schemas, unwrap, validationMessages } from "../api/client";
import EstimateResults from "../components/EstimateResults";
import SearchForm from "../components/SearchForm";
import { destinationUrl } from "../links";

// The form and its results on one page: the results replace Flask's separate
// results page, and the form stays above them for the next search.
export default function SearchPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const origins = useQuery({
    queryKey: ["origins"],
    queryFn: () => unwrap(api.GET("/api/v1/origins")),
  });
  const destinations = useQuery({
    queryKey: ["destinations"],
    queryFn: () => unwrap(api.GET("/api/v1/destinations")),
  });

  // A mutation, not a query: it runs only when the form is submitted, and it
  // writes - every estimate is saved to this browser's history.
  const estimate = useMutation({
    mutationFn: (request: Schemas["EstimateRequest"]) => unwrap(api.POST("/api/v1/estimates", { body: request })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["searches"] }),
  });

  const errors = validationMessages(estimate.error);

  return (
    <>
      <div className="hero">
        <h1>IL Vacation Budget</h1>
        <p>
          {destinations.data ? `Tracking ${destinations.data.length} destinations` : "Tracking destinations"},
          departing from Israel.
        </p>
      </div>

      {(origins.isPending || destinations.isPending) && <p>Loading...</p>}
      {(origins.error || destinations.error) && (
        <p className="error">Could not load the search form: {(origins.error ?? destinations.error)?.message}</p>
      )}
      {origins.data && destinations.data && (
        <SearchForm
          origins={origins.data}
          destinations={destinations.data}
          isSubmitting={estimate.isPending}
          onEstimate={estimate.mutate}
          onViewDestination={(destinationId, request) =>
            navigate(
              destinationUrl(destinationId, {
                ...request,
                currency: request.budget_currency,
                budget: request.budget_amount,
                tier: request.hotel_tier,
              }),
            )
          }
        />
      )}

      {estimate.error && (
        <div className="error">
          {errors.length > 0 ? (
            <ul>
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : (
            `The estimate failed: ${estimate.error.message}`
          )}
        </div>
      )}

      {/* A new key per search: React builds a fresh EstimateResults, so the
          tier picked for the last search doesn't carry over to this one. */}
      {estimate.data && (
        <EstimateResults key={estimate.data.search_id} request={estimate.variables} response={estimate.data} />
      )}
    </>
  );
}
