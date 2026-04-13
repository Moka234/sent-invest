import { defineStore } from 'pinia'

export const useDataStore = defineStore('data', {
  state: () => ({
    /** @type {null|object} */
    dashboardData: null,
    /** @type {null|object} */
    currentUserProfile: null,
  }),
  actions: {
    setDashboard(data) {
      this.dashboardData = data
    },
    setCurrentUserProfile(profile) {
      this.currentUserProfile = profile
    },
    clearCurrentUser() {
      this.currentUserProfile = null
    },
  },
})
