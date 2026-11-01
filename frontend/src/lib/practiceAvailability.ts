type PracticeAvailability = {
  hasActiveProfile: boolean;
  selected: boolean;
  starting: boolean;
  sessionLimitReached: boolean;
};

export function canStartNewPractice({
  hasActiveProfile,
  selected,
  starting,
  sessionLimitReached,
}: PracticeAvailability) {
  return hasActiveProfile && !selected && !starting && !sessionLimitReached;
}
