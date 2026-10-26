import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ApplyFlow } from './ApplyFlow';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <ApplyFlow />
    </MemoryRouter>
  );
});
