FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Must run before `build`: this writes public/widget.js, which `vite build`
# then copies into dist/ as part of its normal "copy public/ to output"
# behavior. public/widget.js is gitignored (a build artifact), so without
# this step dist/widget.js never exists -- nginx's SPA catch-all silently
# serves index.html for it instead (200 OK, wrong content-type), which
# Chrome's ORB then blocks when the widget script tag tries to load it.
RUN npm run build:widget
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
