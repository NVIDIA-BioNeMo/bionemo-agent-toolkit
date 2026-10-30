// A timeout may cancel preparation, but cannot undo an in-progress viewer update.
export function navigationRequest(current) {
  let state = 'preparing';
  return {
    current: () => state === 'preparing' && current(),
    beginCommit() {
      if (state !== 'preparing' || !current()) throw Error('The design changed; open the structure again.');
      state = 'committing';
    },
    expire() {
      if (state === 'preparing') { state = 'cancelled'; return true; }
      return false;
    },
    settle() { state = 'settled'; },
    get state() { return state; }
  };
}
