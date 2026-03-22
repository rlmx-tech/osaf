/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        osaf: {
          unprovoked: "#e74c3c",
          provoked: "#f39c12",
          boat_bite: "#3498db",
          scavenge: "#9b59b6",
          aquaria: "#1abc9c",
          doubtful: "#95a5a6",
          no_assignment: "#bdc3c7",
          not_confirmed: "#ecf0f1",
        },
      },
    },
  },
  plugins: [],
};
