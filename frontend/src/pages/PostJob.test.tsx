import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PostJob } from './PostJob';

test('renders without crashing', () => {
  render(
    <MemoryRouter>
      <PostJob />
    </MemoryRouter>
  );
});
