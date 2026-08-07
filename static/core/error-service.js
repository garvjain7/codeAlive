/**
 * CodeAlive — error-service.js
 * Centralized Error Translation & UX Notification Service
 */

/**
 * Translates HTTP status codes, Error objects, network failures, and backend details
 * into clean, user-friendly messages. Never exposes raw SQL/Python stack traces.
 */
export function translateError(err, fallbackMsg = "Something went wrong. Please try again.") {
  if (!err) return fallbackMsg;

  if (typeof err === "string") {
    return cleanTechnicalText(err, fallbackMsg);
  }

  if (err instanceof TypeError || err.name === "TypeError" || (err.message && err.message.toLowerCase().includes("fetch"))) {
    return "Unable to connect. Please check your internet connection and try again.";
  }

  const status = err.status || err.statusCode;
  const detail = err.detail || err.message || "";

  if (status === 400) {
    return cleanTechnicalText(detail, "Please check your input and try again.");
  }
  if (status === 401) {
    return "Authentication required. Please log in to continue.";
  }
  if (status === 403) {
    return cleanTechnicalText(detail, "Access denied. Incorrect password or permissions.");
  }
  if (status === 404) {
    return cleanTechnicalText(detail, "The requested item was not found.");
  }
  if (status === 410) {
    return "This shared link has expired and is no longer available.";
  }
  if (status === 429) {
    return "Too many attempts. Please wait a moment and try again.";
  }
  if (status >= 500) {
    return "Something went wrong on our end. Please try again in a moment.";
  }

  return cleanTechnicalText(detail, fallbackMsg);
}

function cleanTechnicalText(text, fallback) {
  if (!text) return fallback;

  const isTechnical = /psycopg2|sqlalchemy|InternalServerError|OperationalError|Traceback|syntax error|object at 0x|KeyError|AttributeError|TypeError/i.test(text);
  if (isTechnical) {
    return "An unexpected server error occurred. Please try again later.";
  }

  return text;
}
