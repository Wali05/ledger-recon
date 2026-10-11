import { KeyIcon } from "./Icons";
import { useState } from "react";

export default function SignIn({ onSubmit, error }) {
  const [key, setKey] = useState("");
  return (
    <section className="signin-card" aria-labelledby="signin-title">
      <h2 id="signin-title">Sign in to review</h2>
      <p>
        This workspace requires an API key. Your key identifies you in the
        review history and is kept only for this browser tab.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (key.trim()) onSubmit(key.trim());
        }}
      >
        <label className="note-label" htmlFor="api-key">
          API key
        </label>
        <input
          id="api-key"
          className="signin-input"
          type="password"
          autoComplete="current-password"
          value={key}
          onChange={(event) => setKey(event.target.value)}
        />
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <button className="action-btn success" type="submit">
          <KeyIcon size={15} />
          Sign in
        </button>
      </form>
    </section>
  );
}
