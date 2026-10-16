# Belay

Belay provides assignment-related tutoring to authorized learners. This glossary
supports the [platform integration review](docs/platform-integration-v0.1.md).
Proposed cross-service mechanisms in that review are not claims of implemented connectivity.

## Language

**Platform assignment version**: A version of an assignment published by Cairn,
identifying a learning activity and its materials.
_Avoid_: learner submission commit, grading-policy commit

**Content version**: The identity of a version of a Belay exercise and its tutoring
content. Integration requires explicit mapping from a platform assignment version.
_Avoid_: learner code commit

**Learner pseudonym**: The stable opaque learner identifier supplied by Cairn in Greg's
platform direction, not a name or email. Binding it to credentials and Belay's current
alias format remains proposed; identical aliases across classes do not imply shared state.
_Avoid_: username, email

**Access authorization**: Permission to use a specified assignment/content version
in an institution and class; authentication alone does not establish it.
_Avoid_: login status, research consent

**Participant initialization**: Establishing a scoped pseudonymous record for course
operation, without creating an account, enrollment or research participation.
_Avoid_: account registration, consent to tutor

**Pedagogical mode**: The study or teach activity selection, distinct from tutoring stance.
_Avoid_: tutoring stance

**Tutoring stance**: The peer, oracle or control behavior selection. A valid stance
value does not establish permission to use it in an assignment.
_Avoid_: pedagogical mode, access authorization

**Operational records**: Records needed for scoped course functionality, workload
control, recovery and accounting, distinct from saved dialogue and research use.
_Avoid_: research dataset, saved conversation

**Optional conversation saving**: A separate learner choice to retain eligible dialogue
under a configured policy, enabling authorized restoration/deletion without research consent.
_Avoid_: research participation, unsaved job recovery

**Research consent**: The separately recorded choice governing research participation
and data use; it does not grant course access or enable conversation saving.
_Avoid_: permission to tutor, permission to restore dialogue

**Tutoring operation**: One Belay tutoring action that may require several inference
requests for planning, generation, evaluation or revision.
_Avoid_: one provider call

**Belay inference attempt**: One dispatch from Belay to Portage under the proposed
integration contract, associated with a local reservation and tutoring operation.
_Avoid_: provider attempt, whole student conversation

**Provider attempt**: One upstream inference attempt inside Portage, including a
retry or fallback, associated with its originating Belay inference attempt.
_Avoid_: new Belay request

**Billing scope**: Trusted accounting attribution derived from authorized platform
context, not a browser-selected entitlement or class-access permission.
_Avoid_: learner-supplied billing tag

**Accounting receipt**: A proposed versioned Portage report of an inference attempt's
accounting state and constituent provider attempts, bound to a trusted billing scope.
_Avoid_: model answer, proof of pedagogical safety

**Reservation**: Capacity or money held against possible usage until accounting
resolves it. A local hold and its corresponding Portage charge are not two expenses.
_Avoid_: additional charge, final invoice

**Unknown liability**: Potentially incurred usage whose final cost is not established.
It remains reserved pending reconciliation, even when an answer has been delivered.
_Avoid_: free call, refund, available balance
