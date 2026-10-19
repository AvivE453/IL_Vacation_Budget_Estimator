import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { api, type Schemas, unwrap, validationMessages } from "../api/client";
import EstimateResults from "../components/EstimateResults";
import SearchForm from "../components/SearchForm";
import { destinationUrl } from "../links";

// The form and its results on one page, so the form stays above them for the
// next search.
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
        <h1>לאן טסים בתקציב שלך?</h1>
        <p>
          משווים טיסה ומלון ל-{destinations.data ? destinations.data.length : ""} יעדים ביציאה מישראל, ומוצאים את
          החופשה שמתאימה לכיס.
        </p>
      </div>

      {(origins.isPending || destinations.isPending) && <p>טוען...</p>}
      {(origins.error || destinations.error) && (
        <p className="error">לא הצלחנו לטעון את טופס החיפוש: {(origins.error ?? destinations.error)?.message}</p>
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
        <div className="error" role="alert">
          {errors.length > 0 ? (
            <ul>
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : (
            `החיפוש נכשל: ${estimate.error.message}`
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
