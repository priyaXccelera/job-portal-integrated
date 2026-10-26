import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SavedSearches } from './SavedSearches';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <SavedSearches />
    </MemoryRouter>
  );
});
