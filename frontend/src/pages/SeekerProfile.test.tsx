import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SeekerProfile } from './SeekerProfile';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <SeekerProfile />
    </MemoryRouter>
  );
});
