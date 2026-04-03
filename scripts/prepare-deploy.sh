#!/bin/bash
# Copies private SwissJS packages into the repo for deployment
# Run before docker build or Railway deploy

KIBOLOGIC=~/office/departments/engineering/projects/active/kibologic

echo "Cleaning existing bundled packages..."
rm -rf packages/swite packages/swiss-lib

echo "Copying swite..."
cp -r $KIBOLOGIC/swite packages/swite

echo "Copying swiss-lib..."  
cp -r $KIBOLOGIC/swiss-lib packages/swiss-lib

# Remove node_modules from bundled packages to keep repo clean
rm -rf packages/swite/node_modules
rm -rf packages/swiss-lib/node_modules

echo "Done. Ready for deployment."
