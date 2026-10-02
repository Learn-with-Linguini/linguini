import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, IconButton } from "../components/ui";
import { ChevronLeftIcon, ChevronRightIcon } from "../components/icons";

const steps = [
  {
    id: "find",
    title: "Find words in your world",
  },
  {
    id: "learn",
    title: "Learn by playing I Spy",
  },
  {
    id: "use",
    title: "Use new words in your stories",
  },
] as const;

export function Welcome() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const current = steps[step];

  const move = (direction: -1 | 1) => {
    setStep((currentStep) => (currentStep + direction + steps.length) % steps.length);
  };

  return (
    <div className="welcome-page">
      <img
          className="mascot welcome-logo"
          src="/linguini-logo.png"
          width={120}
          height={120}
          alt="Linguini mascot"
      />
      <section className="welcome-story" aria-live="polite">
        <div className="welcome-story__copy">

          <h2>{current.title}</h2>

        </div>

        <div className={`welcome-demo welcome-demo--${current.id}`}>
          {current.id === "find" ? (
            <div className="welcome-scene">
              <img src="/scenes/grocery-store.jpg" alt="A grocery store full of objects to learn" />
              <i style={{ left: "24%", top: "58%" }}>1</i>
              <i style={{ left: "67%", top: "38%" }}>2</i>
              <i style={{ left: "82%", top: "69%" }}>3</i>
              <div className="welcome-scene__words">
                <span>la manzana</span>
                <span>la cesta</span>
                <span>la tienda</span>
              </div>
            </div>
          ) : null}

          {current.id === "learn" ? (
            <div className="welcome-ispy">
              <img src="/scenes/classroom.jpg" alt="A classroom used for an I Spy activity" />
              <div className="welcome-ispy__clue">
                <strong>Veo algo que está sobre la mesa.</strong>
                <span>I spy something that is on the table.</span>
              </div>
              <div className="welcome-ispy__choices">
                <span>el libro</span>
                <span>la silla</span>
                <span>la mesa</span>
              </div>
            </div>
          ) : null}

          {current.id === "use" ? (
            <div className="welcome-journal">
              <div className="welcome-journal__photos">
                <img src="/scenes/grocery-store.jpg" alt="Grocery store memory" />
                <img src="/scenes/classroom.jpg" alt="Classroom memory" />
              </div>
              <div>
                <span>Saturday, 19 September</span>
                <h3>A few words from today</h3>
                <p>Hoy fui a la tienda. Compré una manzana y practiqué palabras nuevas.</p>
              </div>
            </div>
          ) : null}
        </div>

        <div className="welcome-story__navigation">
          <IconButton label="Previous step" onClick={() => move(-1)}>
            <ChevronLeftIcon />
          </IconButton>
          <div className="welcome-story__dots" aria-label={`Step ${step + 1} of ${steps.length}`}>
            {steps.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={index === step ? "is-active" : ""}
                aria-label={`Show ${item.title}`}
                aria-current={index === step ? "step" : undefined}
                onClick={() => setStep(index)}
              />
            ))}
          </div>
          <IconButton label="Next step" onClick={() => move(1)}>
            <ChevronRightIcon />
          </IconButton>
        </div>
      </section>

      <div className="welcome-actions">
        <Button block onClick={() => navigate("/login?mode=signup")}>
          Get started <ChevronRightIcon size={20} />
        </Button>
        <Button variant="quiet" onClick={() => navigate("/login")}>
          I already have an account
        </Button>
      </div>
    </div>
  );
}
