let selectedSession = null;

let activeExercise = null;
let activeExerciseButton = null;
let exerciseState = "idle";
let activeSessionFile = null;

let calibrationTimer = null;
let calibrationActive = false;

let exerciseNames = {};
let exerciseTargets = {};
let currentProgramProgress = {};
let nextRecommendedExercise = null;
let exerciseInstructions = {};


/* ============================================================
   HELPERS
============================================================ */

function setText(id, value) {
    const element = document.getElementById(id);

    if (element) {
        element.textContent = value;
    }
}


function exerciseFromFilename(filename) {
    if (!filename) {
        return null;
    }

    for (const exercise of Object.keys(exerciseNames)) {
        if (filename.startsWith(exercise + "_")) {
            return exercise;
        }
    }

    return null;
}


function formatSessionDate(value) {
    const date = new Date(
        String(value).replace(" ", "T")
    );

    if (Number.isNaN(date.getTime())) {
        return value;
    }

    return date.toLocaleString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    });
}


/* ============================================================
   PATIENT PLAN
============================================================ */

async function loadPatientPlan() {
    const response = await fetch("/api/plan");
    const plan = await response.json();

    if (!response.ok) {
        throw new Error(
            plan.error || "Could not load patient plan."
        );
    }

    exerciseNames = {};
    exerciseTargets = {};
    exerciseInstructions = {};

    setText(
        "patientName",
        plan.patient || "Patient"
    );

    plan.exercises.forEach(exercise => {
        exerciseNames[exercise.id] = exercise.name;

        exerciseTargets[exercise.id] = {
            sets: exercise.sets,
            repsPerSet: exercise.reps_per_set
        };

        exerciseInstructions[exercise.id] =
            exercise.instructions || "";

        exerciseInstructions[exercise.id] =
            exercise.instructions || "";
    });

    renderExerciseCards(plan.exercises);

    await loadExerciseProgress();
}


function renderExerciseCards(exercises) {
    const grid =
        document.getElementById("exerciseGrid");

    grid.innerHTML = "";

    exercises.forEach((exercise, index) => {
        const card =
            document.createElement("div");

        card.className = "exercise-card";

        card.innerHTML = `
            <div>
                <span class="label">
                    EXERCISE ${index + 1}
                </span>

                <h3>${exercise.name}</h3>

                <p class="exercise-description">
                    ${exercise.sets} sets ×
                    ${exercise.reps_per_set} repetitions
                </p>

                <p class="exercise-instructions">
                    ${exercise.instructions || ""}
                </p>

                <p class="exercise-progress"
                   id="progress-${exercise.id}">
                    Loading progress...
                </p>

                <span class="exercise-status not-started"
                      id="status-${exercise.id}">
                    ○ Not started
                </span>
            </div>

            <button class="exercise-button"
                    data-exercise="${exercise.id}">
                Start exercise
            </button>
        `;

        const button =
            card.querySelector(".exercise-button");

        button.addEventListener(
            "click",
            () => startExercise(exercise.id)
        );

        grid.appendChild(card);
    });
}


/* ============================================================
   PROGRESS
============================================================ */



async function updateProgramOverview(progress) {
    const exercises =
        Object.keys(exerciseTargets);

    let completed = 0;

    exercises.forEach(exercise => {
        const target =
            exerciseTargets[exercise];

        const current =
            progress[exercise] || {
                completed_sets: 0,
                reps_in_set: 0
            };

        if (
            current.completed_sets >=
            target.sets
        ) {
            completed++;
        }
    });

    const total =
        exercises.length;

    const remaining =
        Math.max(
            0,
            total - completed
        );

    setText(
        "completedExercises",
        `${completed} / ${total}`
    );

    setText(
        "remainingExercises",
        remaining
    );

    if (total === 0) {
        setText(
            "programMessage",
            "No rehabilitation exercises are assigned."
        );

    } else if (completed === total) {
        setText(
            "programMessage",
            "Today's rehabilitation program is complete."
        );

    } else {
        setText(
            "programMessage",
            `${remaining} ${
                remaining === 1
                    ? "exercise"
                    : "exercises"
            } remaining today.`
        );
    }
}


async function loadExerciseProgress() {
    try {
        const response =
            await fetch("/api/v2/progress");

        const progress =
            await response.json();

        currentProgramProgress = progress;

        if (!response.ok) {
            throw new Error(
                progress.error ||
                "Could not load progress."
            );
        }

        await updateProgramOverview(
            progress
        );

        updatePatientProgressUI(
            progress
        );

        updateStartNextButton(
            progress
        );


        Object.keys(
            exerciseTargets
        ).forEach(exercise => {

            const target =
                exerciseTargets[exercise];

            const current =
                progress[exercise] || {
                    completed_sets: 0,
                    reps_in_set: 0
                };


            const progressElement =
                document.getElementById(
                    `progress-${exercise}`
                );

            const statusElement =
                document.getElementById(
                    `status-${exercise}`
                );

            const button =
                document.querySelector(
                    `.exercise-button[data-exercise="${exercise}"]`
                );

            const card =
                button
                    ? button.closest(
                        ".exercise-card"
                    )
                    : null;


            if (progressElement) {

                if (
                    current.completed_sets >=
                    target.sets
                ) {
                    progressElement.textContent =
                        `${target.sets}/${target.sets} sets completed`;

                } else {
                    const currentSet =
                        current.completed_sets + 1;

                    progressElement.textContent =
                        `Set ${currentSet} of ${target.sets} · ` +
                        `${current.reps_in_set}/${target.repsPerSet} reps`;
                }
            }


            if (statusElement) {

                statusElement.className =
                    "exercise-status";

                if (
                    current.completed_sets >=
                    target.sets
                ) {
                    statusElement.textContent =
                        "✓ Completed";

                    statusElement.classList.add(
                        "completed"
                    );

                } else if (
                    current.completed_sets > 0 ||
                    current.reps_in_set > 0
                ) {
                    statusElement.textContent =
                        "● In progress";

                    statusElement.classList.add(
                        "in-progress"
                    );

                } else {
                    statusElement.textContent =
                        "○ Not started";

                    statusElement.classList.add(
                        "not-started"
                    );
                }
            }


            if (
                button &&
                exerciseState === "idle"
            ) {
                if (
                    current.completed_sets >=
                    target.sets
                ) {
                    button.disabled = true;
                    button.textContent =
                        "Completed";

                    button.classList.add(
                        "is-completed"
                    );

                    if (card) {
                        card.classList.add(
                            "is-completed"
                        );
                    }

                } else {
                    button.disabled = false;
                    button.textContent =
                        "Start exercise";

                    button.classList.remove(
                        "is-completed"
                    );

                    if (card) {
                        card.classList.remove(
                            "is-completed"
                        );
                    }
                }
            }
        });

    } catch (error) {

        console.error(
            "Progress load error:",
            error
        );

        setText(
            "programMessage",
            "Could not load rehabilitation progress."
        );
    }
}






function updateStartNextButton(progress) {
    const button =
        document.getElementById(
            "startNextExerciseButton"
        );

    if (!button) {
        return;
    }


    nextRecommendedExercise = null;


    for (
        const exercise
        of Object.keys(exerciseTargets)
    ) {
        const target =
            exerciseTargets[exercise];

        const current =
            progress[exercise] || {
                completed_sets: 0,
                reps_in_set: 0
            };


        if (
            current.completed_sets <
            target.sets
        ) {
            nextRecommendedExercise =
                exercise;

            break;
        }
    }


    if (
        nextRecommendedExercise === null
    ) {
        button.style.display =
            "none";

        return;
    }


    button.style.display =
        "inline-block";


    button.textContent =
        `Start ${exerciseNames[nextRecommendedExercise]}`;


    button.disabled =
        exerciseState !== "idle";


    button.onclick = () => {

        if (
            exerciseState !== "idle" ||
            !nextRecommendedExercise
        ) {
            return;
        }


        startExercise(
            nextRecommendedExercise
        );


        const cardButton =
            document.querySelector(
                `.exercise-button[data-exercise="${nextRecommendedExercise}"]`
            );


        if (cardButton) {
            cardButton.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        }
    };
}


function updatePatientProgressUI(progress) {
    const exercises = Object.keys(exerciseTargets);

    if (exercises.length === 0) {
        return;
    }

    let completedRepsEquivalent = 0;
    let totalRepsEquivalent = 0;

    let nextExercise = null;


    exercises.forEach(exercise => {
        const target =
            exerciseTargets[exercise];

        const current =
            progress[exercise] || {
                completed_sets: 0,
                reps_in_set: 0
            };

        const totalForExercise =
            target.sets * target.repsPerSet;

        const completedForExercise =
            Math.min(
                totalForExercise,
                (
                    current.completed_sets *
                    target.repsPerSet
                ) +
                current.reps_in_set
            );

        totalRepsEquivalent +=
            totalForExercise;

        completedRepsEquivalent +=
            completedForExercise;


        const percent =
            totalForExercise > 0
                ? Math.round(
                    (
                        completedForExercise /
                        totalForExercise
                    ) * 100
                )
                : 0;


        const card =
            document
                .querySelector(
                    `.exercise-button[data-exercise="${exercise}"]`
                )
                ?.closest(
                    ".exercise-card"
                );


        if (card) {
            let progressBox =
                card.querySelector(
                    ".exercise-set-progress"
                );

            if (!progressBox) {
                progressBox =
                    document.createElement("div");

                progressBox.className =
                    "exercise-set-progress";

                progressBox.innerHTML = `
                    <div class="exercise-set-progress-text">
                        <span>Exercise progress</span>
                        <strong>${percent}%</strong>
                    </div>

                    <div class="progress-track">
                        <div class="progress-fill"
                             style="width:${percent}%;">
                        </div>
                    </div>
                `;

                const textArea =
                    card.firstElementChild;

                if (textArea) {
                    textArea.appendChild(
                        progressBox
                    );
                }

            } else {
                const strong =
                    progressBox.querySelector(
                        "strong"
                    );

                const fill =
                    progressBox.querySelector(
                        ".progress-fill"
                    );

                if (strong) {
                    strong.textContent =
                        `${percent}%`;
                }

                if (fill) {
                    fill.style.width =
                        `${percent}%`;
                }
            }


            card.classList.remove(
                "next-exercise"
            );

            const oldBadge =
                card.querySelector(
                    ".next-exercise-badge"
                );

            if (oldBadge) {
                oldBadge.remove();
            }
        }


        if (
            nextExercise === null &&
            current.completed_sets <
                target.sets
        ) {
            nextExercise = exercise;
        }
    });


    const overallPercent =
        totalRepsEquivalent > 0
            ? Math.round(
                (
                    completedRepsEquivalent /
                    totalRepsEquivalent
                ) * 100
            )
            : 0;


    setText(
        "overallProgressPercent",
        `${overallPercent}%`
    );


    const overallBar =
        document.getElementById(
            "overallProgressBar"
        );

    if (overallBar) {
        overallBar.style.width =
            `${overallPercent}%`;
    }


    const nextAction =
        document.getElementById(
            "nextAction"
        );


    if (!nextAction) {
        return;
    }


    if (nextExercise === null) {

        nextAction.textContent =
            "Today's rehabilitation is complete. All prescribed exercises have been finished.";

        return;
    }


    const target =
        exerciseTargets[nextExercise];

    const current =
        progress[nextExercise] || {
            completed_sets: 0,
            reps_in_set: 0
        };

    const setNumber =
        current.completed_sets + 1;

    const repsRemaining =
        Math.max(
            0,
            target.repsPerSet -
            current.reps_in_set
        );


    if (
        current.completed_sets === 0 &&
        current.reps_in_set === 0
    ) {
        nextAction.textContent =
            `Next: ${exerciseNames[nextExercise]}. Start set 1 of ${target.sets} and complete ${target.repsPerSet} repetitions.`;

    } else {
        nextAction.textContent =
            `Next: ${exerciseNames[nextExercise]}. Continue set ${setNumber} of ${target.sets}. ${repsRemaining} repetitions remain in this set.`;
    }


    const nextButton =
        document.querySelector(
            `.exercise-button[data-exercise="${nextExercise}"]`
        );

    const nextCard =
        nextButton
            ? nextButton.closest(
                ".exercise-card"
            )
            : null;


    if (nextCard) {
        nextCard.classList.add(
            "next-exercise"
        );

        const textArea =
            nextCard.firstElementChild;

        if (
            textArea &&
            !textArea.querySelector(
                ".next-exercise-badge"
            )
        ) {
            const badge =
                document.createElement(
                    "span"
                );

            badge.className =
                "next-exercise-badge";

            badge.textContent =
                "NEXT";

            textArea.appendChild(
                badge
            );
        }
    }
}


async function showProgramProgress(exercise) {
    try {
        const response =
            await fetch("/api/v2/progress");

        const progress =
            await response.json();

        const target =
            exerciseTargets[exercise];

        const current =
            progress[exercise];

        if (!target || !current) {
            return;
        }

        if (
            current.completed_sets >=
            target.sets
        ) {
            setText(
                "currentExerciseContext",
                `Completed · ${target.sets}/${target.sets} sets`
            );

            return;
        }

        const setNumber =
            current.completed_sets + 1;

        setText(
            "currentExerciseContext",
            `Set ${setNumber} of ${target.sets} · ` +
            `${current.reps_in_set}/${target.repsPerSet} reps`
        );

    } catch (error) {
        console.error(error);
    }
}




function updateLiveSetFeedback(sessionReps = 0) {
    const panel =
        document.getElementById("liveSetProgress");

    if (!panel) {
        return;
    }


    if (
        exerciseState === "idle" ||
        !activeExercise
    ) {
        panel.style.display = "none";
        return;
    }


    const target =
        exerciseTargets[activeExercise];

    if (!target) {
        panel.style.display = "none";
        return;
    }


    const saved =
        currentProgramProgress[activeExercise] || {
            completed_sets: 0,
            reps_in_set: 0
        };


    const repsPerSet =
        target.repsPerSet;


    const startingReps =
        saved.reps_in_set || 0;


    const combined =
        Math.min(
            repsPerSet,
            startingReps + sessionReps
        );


    const remaining =
        Math.max(
            0,
            repsPerSet - combined
        );


    const percent =
        repsPerSet > 0
            ? Math.min(
                100,
                Math.round(
                    (combined / repsPerSet) * 100
                )
            )
            : 0;


    panel.style.display = "block";


    setText(
        "liveSetExercise",
        exerciseNames[activeExercise] ||
        activeExercise
    );


    setText(
        "liveSetReps",
        `${combined} / ${repsPerSet}`
    );


    const bar =
        document.getElementById(
            "liveSetProgressBar"
        );

    if (bar) {
        bar.style.width =
            `${percent}%`;
    }


    const message =
        document.getElementById(
            "liveSetMessage"
        );


    const badge =
        document.getElementById(
            "liveRecordingBadge"
        );


    if (exerciseState === "paused") {

        panel.classList.add(
            "is-paused"
        );

        if (badge) {
            badge.textContent =
                "● Paused";
        }

        if (message) {
            message.classList.remove(
                "target-reached"
            );

            message.textContent =
                remaining === 0
                    ? "Set target reached. Stop the exercise when ready."
                    : `${remaining} repetitions remain in this set.`;
        }

        return;
    }


    panel.classList.remove(
        "is-paused"
    );


    if (badge) {
        badge.textContent =
            "● Recording";
    }


    if (!message) {
        return;
    }


    if (remaining === 0) {

        message.textContent =
            "✓ Set target reached. Pause the exercise when ready.";

        message.classList.add(
            "target-reached"
        );

    } else if (sessionReps === 0) {

        message.textContent =
            `${remaining} repetitions remain in this set.`;

        message.classList.remove(
            "target-reached"
        );

    } else {

        message.textContent =
            `${remaining} ${
                remaining === 1
                    ? "repetition remains"
                    : "repetitions remain"
            } in this set.`;

        message.classList.remove(
            "target-reached"
        );
    }
}




function hideCalibrationPanel() {
    const panel =
        document.getElementById(
            "calibrationPanel"
        );

    if (!panel) {
        return;
    }

    panel.style.display = "none";
    panel.classList.remove("ready");

    calibrationActive = false;

    if (calibrationTimer) {
        clearInterval(calibrationTimer);
        calibrationTimer = null;
    }
}


function startCalibrationCountdown() {
    const panel =
        document.getElementById(
            "calibrationPanel"
        );

    const countdown =
        document.getElementById(
            "calibrationCountdown"
        );

    const progress =
        document.getElementById(
            "calibrationProgress"
        );

    const title =
        document.getElementById(
            "calibrationTitle"
        );

    const message =
        document.getElementById(
            "calibrationMessage"
        );

    const pauseButton =
        document.getElementById(
            "pauseStopButton"
        );


    if (!panel) {
        return;
    }


    calibrationActive = true;

    panel.style.display = "block";
    panel.classList.remove("ready");

    title.textContent =
        "Keep your leg still";

    message.textContent =
        "RehabTrack is calibrating the movement sensor.";

    countdown.textContent = "5";
    progress.style.width = "0%";


    /*
       Do not allow Pause during the 5-second calibration.
    */
    if (pauseButton) {
        pauseButton.style.display = "none";
    }


    let elapsed = 0;
    const total = 5;


    if (calibrationTimer) {
        clearInterval(calibrationTimer);
    }


    calibrationTimer =
        setInterval(() => {

            elapsed++;

            const remaining =
                Math.max(
                    0,
                    total - elapsed
                );

            const percent =
                Math.min(
                    100,
                    (elapsed / total) * 100
                );


            countdown.textContent =
                remaining > 0
                    ? remaining
                    : "READY";

            progress.style.width =
                `${percent}%`;


            if (elapsed >= total) {

                clearInterval(
                    calibrationTimer
                );

                calibrationTimer = null;
                calibrationActive = false;


                panel.classList.add(
                    "ready"
                );


                title.textContent =
                    "Sensor ready";

                message.textContent =
                    "Begin the exercise when you are ready.";


                if (pauseButton) {
                    pauseButton.style.display =
                        "inline-block";

                    pauseButton.style.background =
                        "#e6a23c";

                    pauseButton.textContent =
                        "Pause";

                    pauseButton.disabled =
                        false;
                }


                setText(
                    "currentExerciseContext",
                    "Sensor ready · Begin the exercise"
                );


                /*
                   Keep READY visible briefly,
                   then remove the calibration panel.
                */
                setTimeout(() => {

                    if (
                        exerciseState ===
                        "recording"
                    ) {
                        panel.style.display =
                            "none";
                    }

                }, 1800);
            }

        }, 1000);
}


/* ============================================================
   START EXERCISE
============================================================ */

async function startExercise(exercise) {
    if (exerciseState !== "idle") {
        return;
    }

    const button =
        document.querySelector(
            `.exercise-button[data-exercise="${exercise}"]`
        );

    if (!button) {
        return;
    }


    selectedSession = null;

    document.getElementById(
        "exerciseResult"
    ).style.display = "none";


    setText(
        "currentExerciseName",
        exerciseNames[exercise]
    );

    await showProgramProgress(exercise);

    const context =
        document.getElementById("currentExerciseContext");

    if (context && exerciseInstructions[exercise]) {
        context.innerHTML = `
            <div class="current-instruction">
                ${exerciseInstructions[exercise]}
            </div>
            <div id="currentProgressText"></div>
        `;
    }


    button.disabled = true;
    button.textContent = "Starting...";


    document
        .querySelectorAll(".exercise-button")
        .forEach(other => {
            if (other !== button) {
                other.disabled = true;
            }
        });


    try {
        const response =
            await fetch(
                "/api/start-exercise",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        exercise
                    })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Could not start exercise."
            );
        }


        activeExercise = exercise;
        activeExerciseButton = button;
        exerciseState = "recording";

        const nextButton =
            document.getElementById(
                "startNextExerciseButton"
            );

        if (nextButton) {
            nextButton.disabled = true;
        }

        await loadExerciseProgress();
        updateLiveSetFeedback(0);
        activeSessionFile = data.file || null;


        button.textContent =
            "Recording...";

        button.classList.add(
            "is-recording"
        );


        const card =
            button.closest(".exercise-card");

        if (card) {
            card.classList.add(
                "is-active"
            );
        }


        const pauseButton =
            document.getElementById(
                "pauseStopButton"
            );

        /*
           Logger is already recording because its first
           five seconds are used as the gyro bias period.
           The patient should remain still during that time.
        */

        pauseButton.style.display =
            "none";

        pauseButton.disabled =
            true;


        document.getElementById(
            "resumeExerciseButton"
        ).style.display = "none";


        setText(
            "currentExerciseContext",
            "Calibrating sensor · Keep your leg still"
        );


        startCalibrationCountdown();


    } catch (error) {
        resetExerciseControls();

        alert(
            "Could not start exercise: " +
            error.message
        );
    }
}


/* ============================================================
   PAUSE / STOP
============================================================ */

async function pauseOrStopExercise() {
    if (calibrationActive) {
        return;
    }

    const button =
        document.getElementById(
            "pauseStopButton"
        );

    const resumeButton =
        document.getElementById(
            "resumeExerciseButton"
        );


    /* Recording -> Pause */

    if (exerciseState === "recording") {

        button.disabled = true;
        button.textContent =
            "Pausing...";

        try {
            const response =
                await fetch(
                    "/api/pause-exercise",
                    {
                        method: "POST"
                    }
                );

            const data =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error ||
                    "Could not pause."
                );
            }


            exerciseState = "paused";

            updateLiveSetFeedback(
                Number(
                    document.getElementById("repetitions")?.textContent
                ) || 0
            );


            activeExerciseButton
                .classList.remove(
                    "is-recording"
                );

            activeExerciseButton
                .classList.add(
                    "is-paused"
                );

            activeExerciseButton
                .textContent =
                    "Paused";


            button.disabled = false;
            button.textContent =
                "Stop exercise";

            button.style.background =
                "#c94c4c";


            resumeButton.style.display =
                "inline-block";

            resumeButton.disabled = false;

            setText(
                "currentExerciseContext",
                "Session paused"
            );


        } catch (error) {
            button.disabled = false;
            button.textContent = "Pause";

            alert(
                "Could not pause: " +
                error.message
            );
        }

        return;
    }


    /* Paused -> Stop */

    if (exerciseState === "paused") {

        const finishedExercise =
            activeExercise;


        button.disabled = true;
        button.textContent =
            "Stopping...";

        resumeButton.disabled = true;


        try {
            const response =
                await fetch(
                    "/api/stop-exercise",
                    {
                        method: "POST"
                    }
                );

            const data =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error ||
                    "Could not stop."
                );
            }


            const finishedFile =
                data.file || activeSessionFile;

            resetExerciseControls();

            selectedSession = finishedFile || null;


            setTimeout(
                async () => {

                    if (finishedFile) {
                        await loadSession(
                            finishedFile
                        );
                    } else {
                        await loadSession();
                    }

                    await loadSessions();
                    await loadStatus();

                    await saveAndShowResult(
                        finishedExercise,
                        finishedFile
                    );

                    await loadExerciseProgress();
                    await loadDailyProgressHistory();

                    await showProgramProgress(
                        finishedExercise
                    );
                },
                1200
            );


        } catch (error) {
            button.disabled = false;
            button.textContent =
                "Stop exercise";

            resumeButton.disabled = false;

            alert(
                "Could not stop: " +
                error.message
            );
        }
    }
}


/* ============================================================
   RESUME
============================================================ */

async function resumeExercise() {
    if (exerciseState !== "paused") {
        return;
    }

    const resumeButton =
        document.getElementById(
            "resumeExerciseButton"
        );

    const pauseButton =
        document.getElementById(
            "pauseStopButton"
        );


    resumeButton.disabled = true;

    resumeButton.textContent =
        "Resuming...";


    try {
        const response =
            await fetch(
                "/api/resume-exercise",
                {
                    method: "POST"
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Could not resume."
            );
        }


        exerciseState = "recording";

        updateLiveSetFeedback(
            Number(
                document.getElementById("repetitions")?.textContent
            ) || 0
        );


        activeExerciseButton
            .classList.remove(
                "is-paused"
            );

        activeExerciseButton
            .classList.add(
                "is-recording"
            );

        activeExerciseButton.textContent =
            "Recording...";


        resumeButton.style.display =
            "none";

        resumeButton.disabled = false;

        resumeButton.textContent =
            "Resume exercise";


        pauseButton.style.display =
            "inline-block";

        pauseButton.style.background =
            "#e6a23c";

        pauseButton.textContent =
            "Pause";

        pauseButton.disabled = false;


        setText(
            "currentExerciseContext",
            "Recording session..."
        );


    } catch (error) {
        resumeButton.disabled = false;

        resumeButton.textContent =
            "Resume exercise";

        alert(
            "Could not resume: " +
            error.message
        );
    }
}


/* ============================================================
   RESET CONTROLS
============================================================ */

function resetExerciseControls() {
    hideCalibrationPanel();

    activeExercise = null;
    activeExerciseButton = null;
    exerciseState = "idle";
    activeSessionFile = null;

    const livePanel =
        document.getElementById(
            "liveSetProgress"
        );

    if (livePanel) {
        livePanel.style.display =
            "none";

        livePanel.classList.remove(
            "is-paused"
        );
    }


    document
        .querySelectorAll(".exercise-button")
        .forEach(button => {

            button.disabled = false;
            button.textContent =
                "Start exercise";

            button.classList.remove(
                "is-recording"
            );

            button.classList.remove(
                "is-paused"
            );

            button.classList.remove(
                "is-completed"
            );


            const card =
                button.closest(
                    ".exercise-card"
                );

            if (card) {
                card.classList.remove(
                    "is-active"
                );
            }
        });


    const pauseButton =
        document.getElementById(
            "pauseStopButton"
        );

    pauseButton.style.display = "none";
    pauseButton.disabled = false;
    pauseButton.textContent = "Pause";


    const resumeButton =
        document.getElementById(
            "resumeExerciseButton"
        );

    resumeButton.style.display =
        "none";

    resumeButton.disabled = false;

    resumeButton.textContent =
        "Resume exercise";
}




function getNextExerciseAfter(exercise, progress) {
    const exercises =
        Object.keys(exerciseTargets);

    const index =
        exercises.indexOf(exercise);

    if (index === -1) {
        return null;
    }

    for (
        let i = index + 1;
        i < exercises.length;
        i++
    ) {
        const id = exercises[i];

        const target =
            exerciseTargets[id];

        const current =
            progress[id] || {
                completed_sets: 0,
                reps_in_set: 0
            };

        if (
            current.completed_sets <
            target.sets
        ) {
            return id;
        }
    }

    return null;
}


function buildNextStepMessage(
    exercise,
    progress
) {
    const target =
        exerciseTargets[exercise];

    const current =
        progress[exercise];

    if (!target || !current) {
        return "";
    }


    if (
        current.completed_sets >=
        target.sets
    ) {
        const nextExercise =
            getNextExerciseAfter(
                exercise,
                progress
            );

        if (nextExercise) {
            return (
                `${exerciseNames[exercise]} is complete for today. ` +
                `Next exercise: ${exerciseNames[nextExercise]}.`
            );
        }

        return (
            "Today's rehabilitation program is complete."
        );
    }


    const setNumber =
        current.completed_sets + 1;

    const remaining =
        Math.max(
            0,
            target.repsPerSet -
            current.reps_in_set
        );


    if (current.reps_in_set === 0) {
        return (
            `Set ${current.completed_sets} completed. ` +
            `When ready, begin set ${setNumber} of ${target.sets}.`
        );
    }


    return (
        `${remaining} ${
            remaining === 1
                ? "repetition remains"
                : "repetitions remain"
        } in set ${setNumber}.`
    );
}


/* ============================================================
   SAVE RESULT TO PATIENT PROGRESS
============================================================ */

async function saveAndShowResult(exercise, filename = null) {
    try {
        let sessionUrl = "/api/session";

        if (filename) {
            sessionUrl +=
                "?file=" +
                encodeURIComponent(filename);
        }

        const sessionResponse =
            await fetch(sessionUrl);

        const session =
            await sessionResponse.json();

        if (!sessionResponse.ok) {
            throw new Error(
                session.error ||
                "Could not load result."
            );
        }


        const progressResponse =
            await fetch(
                "/api/v2/progress/update",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        exercise,
                        repetitions:
                            session.repetitions,
                        file:
                            filename || session.file || null
                    })
                }
            );


        const progress =
            await progressResponse.json();

        if (!progressResponse.ok) {
            throw new Error(
                progress.error ||
                "Could not save progress."
            );
        }


        setText(
            "resultExerciseName",
            exerciseNames[exercise]
        );


        if (progress.exercise_completed) {

            setText(
                "resultSet",
                `${progress.sets} / ${progress.sets}`
            );

            setText(
                "resultReps",
                `${progress.reps_per_set} / ${progress.reps_per_set}`
            );

            setText(
                "resultRemaining",
                "0"
            );

            setText(
                "resultMessage",
                "Exercise completed. All prescribed sets are finished."
            );

        } else {

            const currentSet =
                progress.completed_sets + 1;

            const remaining =
                Math.max(
                    0,
                    progress.reps_per_set -
                    progress.reps_in_set
                );


            setText(
                "resultSet",
                `${currentSet} / ${progress.sets}`
            );

            setText(
                "resultReps",
                `${progress.reps_in_set} / ${progress.reps_per_set}`
            );

            setText(
                "resultRemaining",
                remaining
            );


            setText(
                "resultMessage",
                `${remaining} repetitions remaining in set ${currentSet}.`
            );
        }


        const resultBox =
            document.getElementById(
                "exerciseResult"
            );

        resultBox.style.display =
            "block";


    } catch (error) {
        console.error(error);

        alert(
            "Could not save exercise progress: " +
            error.message
        );
    }
}


/* ============================================================
   SESSION DATA
============================================================ */

async function loadSession(filename = selectedSession) {
    try {
        let url = "/api/session";

        if (filename) {
            url +=
                "?file=" +
                encodeURIComponent(filename);
        }


        const response =
            await fetch(url);

        const data =
            await response.json();


        if (!response.ok) {
            return;
        }


        setText(
            "filename",
            data.file
        );

        setText(
            "lastUpdated",
            "Last updated: " +
            new Date().toLocaleTimeString()
        );

        setText(
            "repetitions",
            data.repetitions
        );

        setText(
            "rom",
            data.average_rom
        );

        setText(
            "speed",
            data.average_speed
        );

        setText(
            "cadence",
            data.cadence
        );

        if (
            exerciseState !== "idle" &&
            activeExercise
        ) {
            updateLiveSetFeedback(
                Number(data.repetitions) || 0
            );
        }

        setText(
            "axis",
            `Gyroscope axis: ${data.gyro_axis}`
        );


        const table =
            document.getElementById(
                "repTable"
            );

        table.innerHTML = "";


        data.rep_details.forEach(rep => {
            const row =
                document.createElement("tr");

            row.innerHTML = `
                <td>${rep.rep}</td>
                <td>${rep.rom}°</td>
                <td>${rep.speed}°/s</td>
            `;

            table.appendChild(row);
        });


        drawGraph(data.graph);


        /* Viewing historical file */
        if (
            filename &&
            exerciseState === "idle"
        ) {
            const exercise =
                exerciseFromFilename(
                    data.file
                );

            if (exercise) {
                setText(
                    "currentExerciseName",
                    exerciseNames[exercise]
                );

                setText(
                    "currentExerciseContext",
                    `Saved session · ${data.repetitions} repetitions`
                );
            }

            document.getElementById(
                "exerciseResult"
            ).style.display = "none";
        }


    } catch (error) {
        console.error(
            "Session error:",
            error
        );
    }
}


/* ============================================================
   GRAPH
============================================================ */

function drawGraph(points) {
    const canvas =
        document.getElementById(
            "angleChart"
        );

    if (!canvas) {
        return;
    }

    const ctx =
        canvas.getContext("2d");

    const width =
        canvas.clientWidth;

    const height =
        canvas.clientHeight || 320;

    const scale =
        window.devicePixelRatio || 1;


    canvas.width =
        width * scale;

    canvas.height =
        height * scale;


    ctx.scale(scale, scale);

    ctx.clearRect(
        0,
        0,
        width,
        height
    );


    if (!points || points.length === 0) {
        return;
    }


    const padding = 45;

    const times =
        points.map(p => p.time);

    const angles =
        points.map(p => p.angle);


    const minX =
        Math.min(...times);

    const maxX =
        Math.max(...times);

    let minY =
        Math.min(...angles);

    let maxY =
        Math.max(...angles);


    if (minY === maxY) {
        minY -= 1;
        maxY += 1;
    }


    const mapX = x =>
        padding +
        ((x - minX) /
        (maxX - minX || 1)) *
        (width - padding * 2);


    const mapY = y =>
        height -
        padding -
        ((y - minY) /
        (maxY - minY || 1)) *
        (height - padding * 2);


    ctx.strokeStyle = "#dce4e0";
    ctx.lineWidth = 1;

    ctx.beginPath();

    ctx.moveTo(
        padding,
        padding
    );

    ctx.lineTo(
        padding,
        height - padding
    );

    ctx.lineTo(
        width - padding,
        height - padding
    );

    ctx.stroke();


    ctx.fillStyle = "#718078";
    ctx.font = "12px sans-serif";

    ctx.fillText(
        `${maxY.toFixed(0)}°`,
        5,
        padding + 5
    );

    ctx.fillText(
        `${minY.toFixed(0)}°`,
        5,
        height - padding
    );

    ctx.fillText(
        `${maxX.toFixed(1)} s`,
        width - padding - 35,
        height - 15
    );


    ctx.strokeStyle = "#287a56";
    ctx.lineWidth = 2.5;

    ctx.beginPath();


    points.forEach(
        (point, index) => {

            const x =
                mapX(point.time);

            const y =
                mapY(point.angle);

            if (index === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
    );


    ctx.stroke();
}


/* ============================================================
   SENSOR STATUS
============================================================ */

async function loadStatus() {
    try {
        const response =
            await fetch("/api/status");

        const data =
            await response.json();


        setText(
            "liveDataStatus",
            data.receiving
                ? "Live data: receiving"
                : "Live data: stopped"
        );


        const status =
            document.querySelector(
                ".status"
            );


        if (
            data.connected &&
            data.recording
        ) {
            status.innerHTML =
                '<span class="status-dot"></span> Sensor connected · Recording';

            status.querySelector(
                ".status-dot"
            ).style.background =
                "#36a269";

        } else if (
            data.connected &&
            data.paused
        ) {
            status.innerHTML =
                '<span class="status-dot"></span> Sensor connected · Paused';

            status.querySelector(
                ".status-dot"
            ).style.background =
                "#e6a23c";

        } else if (data.connected) {
            status.innerHTML =
                '<span class="status-dot"></span> Sensor connected';

            status.querySelector(
                ".status-dot"
            ).style.background =
                "#e6a23c";

        } else {
            status.innerHTML =
                '<span class="status-dot"></span> Sensor disconnected';

            status.querySelector(
                ".status-dot"
            ).style.background =
                "#c94c4c";
        }


    } catch (error) {
        console.error(
            "Status error:",
            error
        );
    }
}


/* ============================================================
   SESSION HISTORY
============================================================ */

async function loadSessions() {
    try {
        const response =
            await fetch("/api/sessions");

        const sessions =
            await response.json();


        const container =
            document.getElementById(
                "sessionList"
            );

        if (!Array.isArray(sessions)) {
            return;
        }


        container.innerHTML = "";


        sessions.forEach(session => {

            const card =
                document.createElement("div");

            card.className =
                "session-history-card";


            if (
                selectedSession ===
                session.file
            ) {
                card.classList.add(
                    "selected-session"
                );
            }


            const reps =
                session.repetitions === null
                    ? "No result"
                    : `${session.repetitions} repetitions`;

            const rom =
                session.average_rom === null
                    ? "--"
                    : `${session.average_rom}° ROM`;

            const speed =
                session.average_speed === null
                    ? "--"
                    : `${session.average_speed}°/s`;


            card.innerHTML = `
                <div>
                    <strong class="session-exercise-name">
                        ${session.exercise_name}
                    </strong>

                    <div class="session-history-date">
                        ${formatSessionDate(session.modified)}
                    </div>

                    <div class="session-history-reps">
                        ${reps}
                    </div>

                    <div class="session-history-metrics">
                        <span>${rom}</span>
                        <span>${speed}</span>
                    </div>
                </div>

                <button class="session-view-button">
                    View session
                </button>
            `;


            card
                .querySelector(
                    ".session-view-button"
                )
                .addEventListener(
                    "click",
                    async () => {

                        selectedSession =
                            session.file;

                        await loadSession(
                            selectedSession
                        );

                        await loadSessions();

                        document.getElementById(
                            "exerciseResult"
                        ).style.display =
                            "none";

                        window.scrollTo({
                            top: 0,
                            behavior: "smooth"
                        });
                    }
                );


            container.appendChild(card);
        });


    } catch (error) {
        console.error(
            "History error:",
            error
        );
    }
}



function setTodayDate() {
    const element =
        document.getElementById("todayDate");

    if (!element) {
        return;
    }

    element.textContent =
        new Date().toLocaleDateString(
            [],
            {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric"
            }
        );
}



async function loadDailyProgressHistory() {
    try {
        const response =
            await fetch("/api/v2/progress/history");

        const data =
            await response.json();

        const container =
            document.getElementById(
                "dailyProgressHistory"
            );

        if (!container) {
            return;
        }

        if (
            !response.ok ||
            !data.days
        ) {
            container.textContent =
                "Could not load progress history.";

            return;
        }


        const dates =
            Object.keys(data.days)
                .sort()
                .reverse();


        if (dates.length === 0) {
            container.textContent =
                "No rehabilitation history yet.";

            return;
        }


        container.innerHTML = "";


        const today =
            new Date()
                .toISOString()
                .slice(0, 10);


        dates.forEach(dateString => {

            const progress =
                data.days[dateString];

            const card =
                document.createElement("div");

            card.className =
                "progress-day-card";


            const parsedDate =
                new Date(
                    dateString + "T12:00:00"
                );


            const dateLabel =
                parsedDate.toLocaleDateString(
                    [],
                    {
                        year: "numeric",
                        month: "short",
                        day: "numeric"
                    }
                );


            const isToday =
                dateString === today;


            let exercisesHTML = "";


            Object.keys(exerciseTargets)
                .forEach(exercise => {

                    const target =
                        exerciseTargets[exercise];

                    const current =
                        progress[exercise] || {
                            completed_sets: 0,
                            reps_in_set: 0
                        };


                    let progressText = "";


                    if (
                        current.completed_sets >=
                        target.sets
                    ) {

                        progressText =
                            `✓ ${target.sets}/${target.sets} sets`;

                    } else {

                        const currentSet =
                            current.completed_sets + 1;

                        progressText =
                            `Set ${currentSet}/${target.sets} · ` +
                            `${current.reps_in_set}/${target.repsPerSet} reps`;
                    }


                    const completeClass =
                        current.completed_sets >=
                        target.sets
                            ? "progress-complete"
                            : "";


                    exercisesHTML += `
                        <div class="progress-day-exercise">

                            <strong>
                                ${exerciseNames[exercise]}
                            </strong>

                            <span class="${completeClass}">
                                ${progressText}
                            </span>

                        </div>
                    `;
                });


            card.innerHTML = `
                <div class="progress-day-header">

                    <strong>
                        ${dateLabel}
                    </strong>

                    ${
                        isToday
                            ? '<span class="today-badge">TODAY</span>'
                            : ""
                    }

                </div>

                <div class="progress-day-exercises">
                    ${exercisesHTML}
                </div>
            `;


            container.appendChild(card);
        });


    } catch (error) {

        console.error(
            "Daily history error:",
            error
        );
    }
}


/* ============================================================
   START PAGE
============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    async () => {

        setTodayDate();

        document.getElementById(
            "pauseStopButton"
        ).addEventListener(
            "click",
            pauseOrStopExercise
        );


        document.getElementById(
            "resumeExerciseButton"
        ).addEventListener(
            "click",
            resumeExercise
        );


        try {
            await loadPatientPlan();
        } catch (error) {
            console.error(error);

            document.getElementById(
                "exerciseGrid"
            ).textContent =
                "Could not load patient plan.";
        }


        await loadSession();
        await loadStatus();
        await loadSessions();
        await loadDailyProgressHistory();


        setInterval(
            loadSession,
            1000
        );

        setInterval(
            loadStatus,
            1000
        );

        setInterval(
            loadExerciseProgress,
            3000
        );

        setInterval(
            loadSessions,
            5000
        );

        setInterval(
            loadDailyProgressHistory,
            5000
        );
    }
);
